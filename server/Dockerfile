FROM python:3.12-slim AS runtime

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

# Copied after the dependency sync so re-numbering a build does not invalidate it.
# api.py resolves the build number relative to the package: parents[3]/web/BUILD_NUMBER.
COPY web/BUILD_NUMBER /app/web/BUILD_NUMBER

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
