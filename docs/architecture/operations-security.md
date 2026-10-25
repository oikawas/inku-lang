# Operations and security

## Authentication and authorization

ChatGPT connection APIs add explicit enablement, mode, startup and owner checks to the existing session guard. HTTP returns only personal nonsecret state; self-hosted authorization uses Mac loopback and protected transfer of one sealed registration. Host-owned keys, exclusive refresh ownership, pinned profile/generation and communication cancellation are specified in the [connection guide](../guide/chatgpt-plan.md).

- When local authentication is enabled, login passes a sliding-window rate limit keyed by client identifier and username.
- Passwords use salted PBKDF2-SHA256. A missing user still runs a dummy hash to reduce a simple timing distinction.
- The DB stores a session-token hash. Clients present a Bearer token or `HttpOnly`, `SameSite=Lax` cookie; the secure flag is configured by environment.
- The permission groups are `admins`, `leaders`, and `users`, and one user may hold several. `_current_user`, `_user_manager`, and `_admin_user` guard routes, and each guard asks a single predicate about membership. The `role` column remains as a mirror derived from the memberships and is read by no decision. A leader who is not an administrator sees and manages only the accounts in their own user group: they can create only members whose sole permission group is `users`, and cannot move a member out of their group with any `group_id`, null included (403). A change that would remove the last administrator is refused with 409.
- Of 138 routes, only the reasoned five-path allowlist (`/health`, `/api/info`, `/api/auth/login`, `/api/notices`, `/api/notices/{notice_id}`) has no guard; a live-route test enumerates it. The shared pipeline's `/api/pipeline/*` requires `_current_user` on each route and passes the authenticated user to every operation as the owner of the execution, variation, and history. Another user's executions and history links are invisible because the owner does not match.
- A client cannot send snapshots, authority sidecars, effect results, resource policies, or the `render` command. Resource limits resolve from the installation manifest and administrator settings, and a work's saved budget cannot be raised. A saved Score cannot declare its own budget either; only a work with a Server-owned history link is replayed under its saved policy.
- `/api/pipeline/images` receives an image input (up to 32 MiB; beyond that, 413 `image_too_large`), and the pixels stay only in that worker's memory. An image waiting to start expires after 15 minutes, and a start after expiry stops with `image_missing`. Only the reference (format, pixel size, SHA-256, byte count) and the provenance cross the durable boundary into the history row; the image bytes are saved neither in the DB nor in work files. For an effect that sends an image, the provider observation keeps only the request body's SHA-256 and byte count, and a provider's refusal body is not read either (it may echo the image).
- Only with `INKU_DEVELOPER_MODE` enabled can a request set `developer_disable_llm_retries` (limits every LLM stage to one attempt), `developer_capture_provider_io` (records raw provider traffic) and `developer_colors_stage` (gives the color stage, a default, also to a run whose saved configuration has none). The request is sent only if its record could be created first; the record holds no URL, header, credential, connection configuration, or exception text, and only the same owner reads it through `/api/pipeline/executions/{id}/provider-observations`. Outside developer mode these options are rejected.
- Request-body, process-wide request, and render concurrency limits are independent.

```mermaid
flowchart LR
    CLIENT["Client"]
    LIMIT["Body / request limit"]
    SESSION["Session dependency"]
    ROLE["Role guard"]
    ROUTE["Protected endpoint"]
    DB[("Session and user DB")]

    CLIENT --> LIMIT
    LIMIT --> SESSION
    SESSION -->|"token comparison"| DB
    DB --> SESSION
    SESSION --> ROLE
    ROLE --> ROUTE
```

## Workers, queues, and persistence priority

| Owner | Capacity | On full queue or timeout |
|---|---|---|
| HTTP middleware | In-flight request limit | 503 with `Retry-After` |
| Render capacity | Concurrent render limit, mutable through DB settings. Replay of saved Scores goes through the same limit | Immediate 503 |
| Pipeline worker pool | `max_workers` threads (default 4), retained runs `max_retained_runs` (default 8), effects advanced per run `max_effect_steps` (default 32) | 429 `pipeline_capacity_reached` when every retained run is busy. The effect-step cap stops as `pipeline_effect_limit` (it is not a replacement retry policy) |
| Pipeline envelope | 16 MiB input, 32 MiB snapshot, 64 MiB output, 1 MiB provider response | The core rejects oversize input before any state change |
| Image intake | 32 MiB per image, 15 minutes waiting to start, pixels in the worker's memory until the run ends | 413 `image_too_large` when over; a start after expiry stops with `image_missing` |
| Autonomous refinement runner | One thread per run (pool default 4); one running run per owner | A second run gets 409 `autonomous_run_running`; while stopping, 503 `autonomous_closing`. When the pipeline workers are full, it waits 3 seconds at a time and goes on |
| Thumbnail pool | A pool of spawned child processes (`INKU_THUMBNAIL_WORKERS`) and a bounded queue | A work that is not accepted or fails is not baked; the listing draws the saved SVG. The parent process writes |
| Work-file executor | Bounded workers and slots | Preserve DB history; skip only the file job |

## DB backup, logs, and output

```mermaid
flowchart TD
    API["FastAPI process"]
    DB[("Canonical DB")]
    SCHED["Lifespan scheduler"]
    BACKUP[("SQLite replica generations")]
    SAVEQ["Work-file queue"]
    OUTPUT[("Work files")]
    LOGPOL["Log retention policy stored in DB"]
    LOGFILE[("Rotating application log")]
    STDOUT["stdout / platform log"]

    API --> DB
    API --> SCHED
    SCHED -->|"due check"| DB
    SCHED -->|"SQLite only"| BACKUP
    API --> SAVEQ
    SAVEQ -.->|"best effort"| OUTPUT
    DB --> LOGPOL
    LOGPOL --> LOGFILE
    API --> STDOUT
```

- Lifespan owns the scheduler and periodically calls `ensure_scheduled_db_backup`; manual and scheduled generations remain distinct.
- Replica backup is unsupported for non-file DBs.
- Where each autonomous refinement run stands is kept in a separate SQLite beside the canonical DB (`<name>-autonomous-runs.db`; `INKU_AUTONOMOUS_RUNS_DB_URL` names another place). It holds no record of a work (each child's move stays on its lineage edge), and the DB backup copies only the canonical DB file. A run the Server was taking when it stopped reads as interrupted at the next start.
- The application applies log retention and also keeps stdout; container-daemon limits are another layer.
- The shared pipeline's compiler results go to the log as `pipeline_compiler_outcome`, with only diagnostic counts and a safe projection limited to short ASCII identifiers. Source text, provider responses, and prompts are never written.
- Work-file output covers description, DDL, Score with metadata, SVG, and PNG. This document does not record actual deployment paths or values.

## Distribution visible in the public repository

Environment-specific local deployment is outside this document. Public sources confirm that:

1. Git is canonical for public source.
2. Compose defines API/Web services and API persistence.
3. Compose carries Web and API health checks.
4. A release-tag workflow builds both services for multiple architectures and publishes only on a tag push.

## Environment-variable categories

Values were not examined.

| Category | Examples of names |
|---|---|
| DB and backup | `INKU_DB_URL`, `INKU_DB_BACKUP_DIR`, `INKU_DB_BACKUP_SCHEDULER`, `INKU_AUTONOMOUS_RUNS_DB_URL` |
| Output and logs | `INKU_OUTPUT_DIR`, `INKU_OUTPUT_SAVE_WORKERS`, `INKU_LOG_DIR` |
| Capacity | `INKU_MAX_CONCURRENT_REQUESTS`, `INKU_RENDER_CONCURRENCY`, `INKU_THUMBNAIL_WORKERS`, `INKU_THUMBNAIL_QUEUE_LIMIT` |
| Pipeline | `INKU_PIPELINE_CONFIG`, `INKU_DEVELOPER_MODE`, `INKU_LLM_REQUEST_TIMEOUT_SECONDS`, `INKU_LLM_RETRY_ATTEMPTS`, `INKU_LLM_RETRY_BASE_DELAY`, `INKU_LLM_STAGE1_ATTEMPT_TIMEOUT_SECONDS`, `INKU_LLM_STAGE1_TOTAL_TIMEOUT_SECONDS`, `INKU_IMAGE_DDL_MAX_TOKENS` |
| Auth | `INKU_SESSION_COOKIE_SECURE`, `INKU_LOGIN_RATE_ATTEMPTS`, `INKU_REDIS_URL` |
| Providers | Provider API-key/base-URL variable names only; never values |

## Evidence map

Evidence: `API-AUTH`, `API-LIMIT`, `PIPE-HOST`, `PIPE-LIMITS`, `PIPE-IMAGE`, `PIPE-REFINE`, `DATA-IMAGE`, `SYS-BACKUP`, `SYS-LOG`, `SYS-FILES`, `OPS-COMPOSE`; implementation in `deps.py`, `auth.py`, `security.py`, `state.py`, `routers/users.py`, `pipeline_api.py`, `pipeline_defaults.py`, `pipeline_product.py`, `pipeline_images.py`, `provider_observation.py`, `autonomous_refine.py`, `db.py`, `logging_setup.py`, and `compose.yaml`.
