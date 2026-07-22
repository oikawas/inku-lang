# inku Setup

This document describes how to run the `inku` server, web UI, and CLI from a source distribution package.

## Package Contents

The source tarball contains only public files tracked by Git.

Included:

- `server/`: FastAPI backend
- `web/`: SvelteKit frontend
- `cli/`: `inku-cli`
- `manual/`: user manuals
- `README*.md`, `SPEC*.md`, `SETUP*.md`, `LICENSE`

Excluded:

- `no-git-sync/`
- `.env` / `.env.local`
- API keys, local user data, local server details
- SQLite databases, history data, generated drawings, `cli/out/`
- `node_modules/`, `.venv/`, build caches

## Requirements

- Python 3.10 or newer
- `uv`
- Node.js 20 or newer is recommended
- npm
- An OS environment where CairoSVG works when PNG export is needed

## Unpack

```sh
tar xzf inku-lang-source-<build>.tar.gz
cd inku-lang-source-<build>
```

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

## Notes

- Do not place secrets in the distribution tarball.
- If you use `.env`, create it locally and do not commit or redistribute it.
- Databases, history records, and generated drawings are runtime data and are not part of the source package.
- If the Web UI is exposed beyond localhost, configure TLS, secure cookies, a reverse proxy, firewall rules, and user management for your deployment environment.
