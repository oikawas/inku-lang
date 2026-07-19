FROM python:3.10-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_PREFERENCE=only-system

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates libcairo2 \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv

WORKDIR /app
COPY shared/ /app/shared/
COPY server/ /app/server/
RUN cd /app/server && uv sync --frozen --no-dev

RUN useradd --create-home --uid 10001 inku \
    && mkdir -p /data/outputs /data/db-backups /data/cache \
    && chown -R inku:inku /data

USER inku
WORKDIR /app/server
ENV PATH="/app/server/.venv/bin:${PATH}" \
    INKU_SERVER_HOST=0.0.0.0 \
    INKU_SERVER_PORT=8100 \
    INKU_DB_URL=sqlite:////data/inku.db \
    INKU_SECRET_KEY_FILE=/data/secret.key \
    INKU_OUTPUT_DIR=/data/outputs \
    INKU_DB_BACKUP_DIR=/data/db-backups \
    UV_CACHE_DIR=/data/cache

EXPOSE 8100
CMD ["inku-server"]
