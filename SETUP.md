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
- `resvg-py` when PNG export is needed (installed by `uv sync`)

To run in containers:

- Docker Engine and Docker Compose v2

### About PNG output

PNG conversion goes through **resvg alone. There is no fallback**. Where resvg is absent, PNG output raises instead of degrading quietly.

CairoSVG used to stand behind it. It does not implement `feTurbulence` / `feDisplacementMap` / `feGaussianBlur`, and rather than failing it **drops them**: the ground grain and the material filters (pencil / crayon / chalk / brush_thick) vanished from the PNG, which came back looking clean. A rasterizer that quietly returns the wrong picture is worse than one that is missing. The backend in use and its version are logged once at server startup.

## Unpack

```sh
tar xzf inku-lang-source-<build>.tar.gz
cd inku-lang-source-<build>
```

## Working from a git clone

`web/BUILD_NUMBER` is a shared counter, so two branches bumping it is never a
real disagreement -- a merge driver keeps the larger number. Merge drivers live
in `.git/config`, which is not versioned, so run this immediately after cloning:

```sh
scripts/git/setup.sh
```

Worktrees share `.git/config`, so one run covers all of them. If it was missed,
`make test`, `make test-server`, `make test-cli`, and `make test-web` from the
repository root apply the same setup idempotently before testing.

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
If that password is lost, the web UI cannot hand it back and `.env` is no longer read. `inku-admin reset-password` sets it from inside the server's own environment — `docker compose exec api inku-admin reset-password --username admin` on the container route, or `uv run inku-admin reset-password --username admin` from this directory. It asks for the new password twice; `--password-stdin` reads it from the first line of standard input instead. Running it means holding the server's container or its files, which already means holding the database.

Optionally set the SQLite DB location. `INKU_DB_URL` accepts SQLite URLs only;
a non-SQLite URL is rejected before engine creation. If unset, the Server
creates a SQLite DB under the user's local data directory.

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

## Using a local Ollama provider

inku can connect to [Ollama](https://ollama.com) through its local OpenAI-compatible endpoint. This is a separately managed setup: the operator installs and runs Ollama, pulls the models, configures the endpoint, and assigns each stage. **It is not a claim that the whole of inku can be used without API keys or authentication settings.** Only the Stage 1 / Stage 2 pair below has been measured. Vision can use the same compatibility path when Ollama serves a model that accepts image input, but the current verified local catalog contains no Vision model and the standard setup does not guarantee one.

### 1. Widen the context length

Install Ollama, then set its context length. **A Stage 2 prompt runs 12,000 to 14,600 tokens, which does not fit in a short context. What overflows is dropped silently, so a reply comes back having read only a fraction of the instructions.**

```sh
export OLLAMA_CONTEXT_LENGTH=16384
```

### 2. Pull two models

**The two stages want different models, so give each its own.**

```sh
ollama pull qwen3.5:4b-q4_K_M                      # Stage 1 (3.4GB)
ollama pull ministral-3:8b-instruct-2512-q4_K_M    # Stage 2 (6.0GB)
```

9.4GB together. **Both stay resident at once**, so budget memory for the pair.

**Name the quantization in the tag.** A bare tag such as `qwen3.5:4b` is replaced upstream over time and comes loose from the notes in the model list.

### 3. Point inku at it

The default endpoint is `http://localhost:11434/v1`, so nothing needs setting when Ollama runs on the same machine. To change it:

```sh
export OLLAMA_BASE_URL='http://localhost:11434/v1'
```

**Inside a container, `localhost` is the container itself** and will not reach an Ollama running on the host. Name the host in `.env`:

```sh
OLLAMA_BASE_URL=http://host.docker.internal:11434/v1
```

That one line is all it takes: `deploy/compose.yaml` already resolves `host.docker.internal`.

### 4. Assign one model per stage

Sign in as an administrator and set these in the model settings:

| Stage | Provider | Model |
| --- | --- | --- |
| Stage 1 | Ollama | `qwen3.5:4b-q4_K_M` |
| Stage 2 | Ollama | `ministral-3:8b-instruct-2512-q4_K_M` |

### Why this pair

**Stage 1** reads a description into instructions, so what matters is whether it writes sentences that stay inside the vocabulary. `qwen3.5:4b-q4_K_M` was the only model that held up in both Japanese and English, and it is also the smallest of the candidates. **Larger does not order better here.**

**Stage 2** builds those instructions into a JSON Score, so what matters is how many of the written sentences reach a shape instruction. `ministral-3:8b-instruct-2512-q4_K_M` carries the most.

The model list carries a note on each of the ten models measured, describing what these two readings found. Consult it when choosing something else you already have.

**A GPU is not required, though it helps.** CPU alone works. How long a single drawing takes varies widely by machine.

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
| `INKU_DB_URL` | SQLite DB URL. Non-SQLite URLs are rejected before engine creation; local SQLite is the default |
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
| `OLLAMA_BASE_URL` | Local Ollama endpoint. Defaults to `http://localhost:11434/v1` |
| `OLLAMA_CONTEXT_LENGTH` | Context length, set on the Ollama side; inku does not read it. **It must be long enough to hold a Stage 2 prompt** |

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
