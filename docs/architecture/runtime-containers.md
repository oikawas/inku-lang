# Runtime containers

“Container” is used here in two senses: a logical C4 runtime unit and a Docker Compose service. In development, Web and FastAPI are separate processes. The backend owns the DB, output, backups, and logs. Compose packages the same two services and places API persistence on a volume.

## Logical runtime units

```mermaid
flowchart TB
    BROWSER["Browser"]
    WEB_PROC["SvelteKit process"]
    API_PROC["FastAPI process"]
    NATIVE_RENDER["inku-render-python wheel\nshared Rust Engine 41 core"]
    STAGE_POOL["Stage executor / bounded queue"]
    SAVE_POOL["Work-file executor / bounded queue"]
    BACKUP_TASK["Lifespan backup scheduler"]
    PROVIDERS["LLM providers"]
    DB[("DB")]
    OUTPUTS[("Work files")]
    BACKUPS[("DB replicas")]
    LOGS[("Application logs + stdout")]

    BROWSER -->|"HTTP"| WEB_PROC
    WEB_PROC -->|"/api proxy"| API_PROC
    API_PROC -->|"one render request"| NATIVE_RENDER
    API_PROC -->|"Stage 0.5 / 1 / 2 job"| STAGE_POOL
    STAGE_POOL -->|"provider call"| PROVIDERS
    API_PROC -->|"transaction"| DB
    API_PROC -->|"best-effort job"| SAVE_POOL
    SAVE_POOL -->|"SVG, JSON, DDL, PNG"| OUTPUTS
    API_PROC -->|"owns"| BACKUP_TASK
    BACKUP_TASK -->|"SQLite replica"| BACKUPS
    API_PROC -->|"rotating file + stream"| LOGS
```

## Compose distribution

```mermaid
flowchart LR
    CLIENT["Client"]
    WEB_IMG["Web service / Node"]
    API_IMG["API service / Python\nCPython native render wheel"]
    WHEEL_BUILDER["Ephemeral pinned Rust / maturin builder"]
    DATA_VOL[("Persistent data volume")]
    PROVIDER["LLM provider"]

    CLIENT -->|"HTTP"| WEB_IMG
    WEB_IMG -->|"internal API URL"| API_IMG
    WHEEL_BUILDER -.->|"audited wheel artifact"| API_IMG
    API_IMG -->|"DB, outputs, backups, logs"| DATA_VOL
    API_IMG -->|"model request"| PROVIDER
```

## Development and Compose

| View | Development | Compose | Evidence |
|---|---|---|---|
| Web | Vite/SvelteKit process proxies `/api` | adapter-node build under Node | `vite.config.ts`; `web/Dockerfile` |
| API | `inku-server` / uvicorn with the locally built native render wheel | Python service runs `inku-server` with a prebuilt CPython native wheel | `server/pyproject.toml`; `server/Dockerfile`; `core/crates/inku-render-python` |
| Native render artifact | Pinned Rust and maturin build the wheel outside the Server package backend | An ephemeral builder creates and audits the wheel; the runtime image contains the accepted wheel, not the toolchain | `rust-toolchain.toml`; `core/crates/inku-render-python/pyproject.toml`; `server/Dockerfile` |
| DB | `INKU_DB_URL`; SQLite by default, PostgreSQL supported in code | Explicit SQLite on the volume | `db.py`; `server/Dockerfile` |
| Persistence | Environment-specific DB and output paths | One persistent volume | Dockerfiles; `compose.yaml` |
| Distribution | Environment-specific and outside this document | Release tag builds and publishes containers | `.github/workflows/release.yml` |

## Evidence map

| Diagram element | Evidence ID | Implementation |
|---|---|---|
| Web/API processes | `SYS-WEB`, `SYS-API` | `hooks.server.ts`, `api.py` |
| Native render boundary | `PIPE-RENDER` | `default/adapter.py`, `inku-render-python`, `inku-render` |
| Stage/file pools | `API-LIMIT`, `SYS-FILES` | `api_core/state.py`, `rendering.py` |
| Backup/logs | `SYS-BACKUP`, `SYS-LOG` | `api.py:_lifespan`, `db.py`, `logging_setup.py` |
| Compose | `OPS-COMPOSE` | `compose.yaml`, Dockerfiles |
