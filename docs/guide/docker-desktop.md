# Getting started with Docker Desktop (ChatGPT plan, single user)

This guide runs inku in containers on Docker Desktop on your own Mac (or Windows) and paints with your ChatGPT subscription's allowance (the [ChatGPT plan connection](chatgpt-plan.md)). It runs in single-user mode, so there is no login screen and no password: the setup belongs to the one person who owns the PC.

The containers are built from your local source with the repository's top-level `compose.yaml`, where single-user mode is the default. The same source is also used on the PC side for the ChatGPT sign-in. To run the GHCR release images with an API key instead, see [`deploy/README.md`](../../deploy/README.md); that setup uses ordinary account sign-in.

This guide applies to versions that support the ChatGPT plan in containers (v2.15.83 and later).

## What you need

Mac:

- [Docker Desktop](https://www.docker.com/products/docker-desktop/), running
- Git
- [`uv`](https://docs.astral.sh/uv/) (`brew install uv` with Homebrew), used for the ChatGPT sign-in on the PC side
- Google Chrome or Brave. The ChatGPT sign-in page opens in this browser
- A ChatGPT subscription. Whether your account can use the plan, and which models it offers, is confirmed by the model list after you authorize

Windows:

- Docker Desktop (WSL 2 backend) and a WSL 2 Linux distribution such as Ubuntu
- Enable that distribution under Docker Desktop's Resources → WSL integration
- Run every command below in a WSL 2 terminal, with Git and `uv` installed inside WSL 2

**The ChatGPT sign-in on Windows (step 4) has not been verified.** The sign-in tooling is written for macOS and Linux and does not run on Windows Python. The steps below run it inside WSL 2 and open the browser on the Windows side, but whether the Windows browser can reach the sign-in return address (`127.0.0.1` inside WSL 2) has not been checked. Steps 1–3 and 5 are the same as on a Mac.

The API container's memory limit defaults to 4 GB (`INKU_API_MEM_LIMIT`). If Docker Desktop has less memory than that, raise it under Docker Desktop's Resources settings.

## 1. Get the source

```sh
git clone https://github.com/oikawas/inku-lang.git
cd inku-lang
```

Run the following commands in this directory unless a step says otherwise.

## 2. Create `.env`

The ChatGPT plan is off by default. To use it in containers, write two settings to `.env`.

```sh
cat > .env <<'EOF'
INKU_CHATGPT_PLAN_ENABLED=1
INKU_CHATGPT_SELF_HOSTED=1
EOF
```

Single-user mode (`INKU_SINGLE_USER=1`) is the default in `compose.yaml`, so you do not need to set it. Single-user mode creates its own account, so `INKU_BOOTSTRAP_ADMIN_PASSWORD` is not needed either. `.env` is excluded from Git.

## 3. Build and start

```sh
docker compose up -d --build
```

The first build also compiles the shared Rust core, so it takes a while. Once it is up, check it:

```sh
docker compose ps
curl http://localhost:8101/health        # {"ok":true}
```

Open <http://localhost:5173> in a browser. There is no login screen. The API answers on <http://localhost:8101> (a different port from the release compose).

## 4. Connect ChatGPT

The ChatGPT sign-in happens on the PC, and its result is handed to the container in a sealed file, because the container cannot receive the return from the sign-in page. After the handover, the container alone holds the sign-in.

### 4-1. Look up your ID

```sh
curl -s http://localhost:8101/api/auth/me
```

Note the value of `"id"` in the JSON (shaped like `xxxxxxxx-xxxx-…`). In single-user mode this works without signing in.

### 4-2. Create the recipient file

Have the container create the public information it needs to receive the sealed file (the recipient). Replace `<your-id>` with the value from 4-1.

```sh
umask 077
docker compose exec -T --user 10001:10001 api \
  inku-chatgpt recipient --owner-id <your-id> > recipient.json
```

`recipient.json` expires after 30 minutes. Finish 4-3 to 4-6 within that time.

### 4-3. Prepare the PC side (first time only)

```sh
cd server
uv sync --frozen --inexact
```

### 4-4. Sign in to ChatGPT and grant access

Run this from the `server` directory. The container's sign-in is kept in its own store (`~/.config/inku-chatgpt-container`) so that it does not mix with any other sign-in on the PC.

```sh
INKU_CHATGPT_PLAN_ENABLED=1 INKU_DEVELOPER_MODE=1 \
  INKU_CHATGPT_AUTH_DIR="$HOME/.config/inku-chatgpt-container" \
  uv run --frozen --no-sync inku-chatgpt authorize --recipient ../recipient.json \
  --browser chrome --language en --consent
```

Chrome opens the ChatGPT sign-in and consent page. Use `--browser brave` for Brave. After you consent, the command prints one line of JSON containing `"status"` and `"profile_id"`. Note the `profile_id` value.

On Windows (WSL 2), pass `--no-browser` instead of `--browser chrome` and open the printed URL in a Windows browser (not verified).

### 4-5. Seal the sign-in

```sh
INKU_CHATGPT_PLAN_ENABLED=1 INKU_DEVELOPER_MODE=1 \
  INKU_CHATGPT_AUTH_DIR="$HOME/.config/inku-chatgpt-container" \
  uv run --frozen --no-sync inku-chatgpt export --recipient ../recipient.json \
  --profile-id <profile_id> --output ../sealed.json
cd ..
```

Sealing removes the sign-in from the PC. From then on, only the container refreshes it.

### 4-6. Import it into the container

```sh
docker compose exec -T --user 10001:10001 api inku-chatgpt import < sealed.json
rm recipient.json sealed.json
```

The import is done when it prints `"status":"imported"`. The two files have served their purpose, so delete them.

## 5. Choose a model and paint

1. In the web settings, open the "ChatGPT plan" tab and press "Check connection".
2. In the "Models" tab of the settings, choose "ChatGPT plan". From "Select models", press "Fetch model list", tick the models to paint with, and save. They are visible only to you.
3. In "Model selection" on the painting screen, choose a ChatGPT plan model as the model shared by Stage 1/2.

Write a short description and paint. If you run out of allowance, check your ChatGPT usage from "Manage usage" in the "ChatGPT plan" tab, and press "Check usage and retry" once it has recovered.

## Stop, update, remove

```sh
docker compose stop                      # stop
docker compose start                     # resume
git pull && docker compose up -d --build # update to a newer version
```

The works database and the ChatGPT sign-in (`/data/chatgpt`) both live in the `inku-data` volume. They survive stopping and recreating the containers. `docker compose down -v` deletes the volume, losing both your works and the ChatGPT connection; start again from step 4 if you do that.

How the ChatGPT plan works, how to disconnect it, and how to read its errors are in [ChatGPT plan connection](chatgpt-plan.md).
