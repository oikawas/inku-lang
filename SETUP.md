# inku Setup

This document describes how to run the `inku` server, web UI, and CLI from a source distribution package.

## Package Contents

The source tarball contains only public files tracked by Git.

Included:

- `server/`: FastAPI backend
- `web/`: SvelteKit frontend
- `cli/`: `inku-cli`
- `shared/`: the package the server and the CLI share
- `manual/`: user manuals
- `docs/`: supporting material
- `android/`: the Android application
- `compose.yaml`, `server/Dockerfile`, `web/Dockerfile`, `.dockerignore`: the definitions that build containers from source
- `deploy/`: the compose file and guide for deploying released images
- `README*.md`, `SPEC*.md`, `SETUP*.md`, `CHANGELOG*.md`, `PROJECT_CONTEXT*.md`, `PLUGIN.md`, `LICENSE`

Excluded:

- `no-git-sync/`
- `server/reference/` (the version-frozen development reference corpus)
- `.env` / `.env.local`
- API keys, local user data, local server details
- SQLite databases, history data, generated drawings, `cli/out/`
- `node_modules/`, `.venv/`, build caches

## Requirements

To run from source:

- Python 3.12 or newer (both `server` and `cli` declare `requires-python = ">=3.12"`)
- `uv`
- Node.js 20 or newer is recommended
- npm
- An SVG rasterizer when PNG export is needed

To run in containers:

- Docker Engine and Docker Compose v2

### About PNG output

PNG conversion **prefers resvg and falls back to CairoSVG**. The fallback still writes PNGs, but **the material filters (pencil / crayon / chalk / brush_thick) are lost from both the PNG and the Vision input**. Which backend is in use is logged once at server startup. PNG output is disabled when no rasterizer is installed at all.

## Unpack

```sh
tar xzf inku-lang-source-<build>.tar.gz
cd inku-lang-source-<build>
```

## Running in Containers

There are two container routes. **[`deploy/README.md`](deploy/README.md) is the authoritative deployment guide**; the first account, data persistence, version pinning, HTTPS and logs are covered there.

### Pull the released images (no build)

Releases are published as container images on GHCR (`ghcr.io/oikawas/inku-api` and `ghcr.io/oikawas/inku-web`, amd64 and arm64). This route builds nothing, so it does not need this tarball either.

```sh
mkdir inku && cd inku
curl -O https://raw.githubusercontent.com/oikawas/inku-lang/main/deploy/compose.yaml
curl -o .env https://raw.githubusercontent.com/oikawas/inku-lang/main/deploy/.env.example
$EDITOR .env   # Fill in INKU_BOOTSTRAP_ADMIN_PASSWORD (8 characters or more) and your LLM API key
docker compose up -d
```

The web UI answers on `http://localhost:5173` and the API on `http://localhost:8100`. Sign in as `admin` with the password from `.env`.

### Build from this source

The `compose.yaml` at the root of the tarball builds images from the source at hand, using `server/Dockerfile` and `web/Dockerfile`. Use it to check a version under development.

```sh
INKU_BOOTSTRAP_ADMIN_PASSWORD='change-this-password' docker compose up -d --build
```

The web UI answers on `http://localhost:5173` and the API is published on `http://localhost:8101` by default (`INKU_WEB_PORT` and `INKU_API_PORT` change these). The DB persists in the `inku-data` volume.

**`INKU_BOOTSTRAP_ADMIN_PASSWORD` is required.** Both compose files refuse to start while it is blank, for the reason given in the next section: there is no self-service registration, so an empty DB with no initial admin offers no way to sign in.

The sections below are the from-source route.

## Server Setup

```sh
cd server
uv sync
```

Set an 8-character-or-longer password before the first startup, so that an initial admin user is created on the new DB.

```sh
export INKU_BOOTSTRAP_ADMIN_PASSWORD='change-this-password'
```

inku has no self-service registration, and only an authenticated admin can create accounts. **An empty DB started without this initial admin offers no way to sign in.** If it was missed, set the password and restart: the account is created then. Nothing happens on a DB that already has users, so an existing password is never overwritten. A blank value counts as unset.

Optionally set the DB location. If unset, the server creates a SQLite DB under the user's local data directory.

```sh
export INKU_DB_URL='sqlite:///./inku.db'
```

API keys may be supplied through environment variables, or registered from the model settings UI after logging in as an admin user. API keys saved from the UI are encrypted in the DB and are never displayed again.

```sh
export OPENAI_API_KEY='...'
export ANTHROPIC_API_KEY='...'
export GEMINI_API_KEY='...'
export NVIDIA_API_KEY='...'
```

Start the API server:

```sh
uv run inku-server
```

The default API URL is `http://127.0.0.1:8100`. To change the listen address:

```sh
export INKU_SERVER_HOST='0.0.0.0'
export INKU_SERVER_PORT='8100'
uv run inku-server
```

Health check:

```sh
curl http://127.0.0.1:8100/health
```

## Web UI Setup

Run this in another terminal:

```sh
cd web
npm install
npm run dev
```

The development server uses `http://127.0.0.1:5173` by default. The Vite configuration proxies Web UI `/api` requests to the API server at `http://127.0.0.1:8100`.

Production-like checks:

```sh
npm run check
npm run build
```

## CLI Setup

Run this in another terminal:

```sh
cd cli
uv sync
```

The CLI connects to `http://127.0.0.1:8100` by default. Use `--base-url` or `INKU_BASE_URL` for another API URL.

```sh
uv run inku-cli --base-url http://127.0.0.1:8100 me
```

Drawing example:

```sh
uv run inku-cli --base-url http://127.0.0.1:8100 paint "A single black line in white space."
```

Save to server history:

```sh
uv run inku-cli --base-url http://127.0.0.1:8100 paint "A blue circle in the upper right." --save-history
```

## Common Environment Variables

| Variable | Purpose |
| --- | --- |
| `INKU_DB_URL` | DB connection URL. SQLite is used by default |
| `INKU_BOOTSTRAP_ADMIN_PASSWORD` | Initial admin password for a new DB. Required to be able to sign in at all; blank counts as unset |
| `INKU_BOOTSTRAP_ADMIN_USERNAME` | Initial admin username. Defaults to `admin` |
| `INKU_SECRET_KEY` | Secret key used to encrypt saved API keys |
| `INKU_SECRET_KEY_FILE` | File path for the generated secret key |
| `INKU_SERVER_HOST` | `inku-server` listen host |
| `INKU_SERVER_PORT` | `inku-server` listen port |
| `INKU_BASE_URL` | Default API URL for `inku-cli` |
| `INKU_STAGE_WORKERS` | Concurrent Stage 1 / Stage 2 LLM calls |
| `INKU_OUTPUT_DIR` | Automatic output-save directory |
| `INKU_OUTPUT_PNG_SIZE` | Automatic output-save PNG Y-axis size |
| `OPENAI_API_KEY` | OpenAI API key |
| `ANTHROPIC_API_KEY` | Claude API key |
| `GEMINI_API_KEY` | Gemini API key |
| `NVIDIA_API_KEY` | NVIDIA API key |

Used only when running in containers:

| Variable | Purpose |
| --- | --- |
| `INKU_IMAGE_TAG` | The image tag `deploy/compose.yaml` pulls. Defaults to `latest`; set it to pin a version |
| `INKU_WEB_PORT` | The host port the web UI is published on. Defaults to `5173` |
| `INKU_API_PORT` | The host port the API is published on. Defaults to `8100` in `deploy/compose.yaml` and to `8101` in the `compose.yaml` that builds from source |
| `INKU_ORIGIN` | The web UI origin. Defaults to `http://localhost:5173` |

## Notes

- Do not place secrets in the distribution tarball.
- If you use `.env`, create it locally and do not commit or redistribute it.
- Databases, history records, and generated drawings are runtime data and are not part of the source package.
- If the Web UI is exposed beyond localhost, configure TLS, secure cookies, a reverse proxy, firewall rules, and user management for your deployment environment. For containers, [`deploy/README.md`](deploy/README.md) covers this under "Serving over HTTPS".
- `.env` is also the file compose reads. The same rule applies: do not commit or redistribute it.
