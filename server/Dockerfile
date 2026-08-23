# This immutable builder contains Rust 1.95.0, maturin 1.13.3, and CPython 3.12.
# Only its audited wheel crosses into the runtime image; Rust and Cargo do not.
FROM ghcr.io/pyo3/maturin@sha256:2519833ac5bf071e02fa231ce368b5b69fac8be1b0774376e3de103f9bed2578 AS native-builder

WORKDIR /build
COPY core/ /build/core/
RUN maturin build \
    --manifest-path /build/core/crates/inku-render-python/Cargo.toml \
    --release \
    --locked \
    --compatibility manylinux2014 \
    --out /wheelhouse

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_PREFERENCE=only-system

# libcairo2 was here for cairosvg, which v2.7.10 removed entirely. resvg-py is
# a wheel and needs no OS library of its own, so nothing in the image links
# against cairo any more.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv

WORKDIR /app
COPY shared/ /app/shared/
COPY server/ /app/server/
COPY --from=native-builder /wheelhouse/ /tmp/wheelhouse/
RUN cd /app/server \
    && uv sync --frozen --no-dev \
    && uv pip install --python /app/server/.venv/bin/python --no-deps /tmp/wheelhouse/*.whl \
    && rm -rf /tmp/wheelhouse

# Copied after the dependency sync so re-numbering a build does not invalidate it.
# api.py resolves the build number relative to the package: parents[3]/web/BUILD_NUMBER.
# APP_VERSION is read the same way (reference.py and api_core/common.py); without it
# the published image answered /api/info with version "unknown" -- ledger I-327.
COPY web/BUILD_NUMBER /app/web/BUILD_NUMBER
COPY web/APP_VERSION /app/web/APP_VERSION

RUN useradd --create-home --uid 10001 inku \
    && mkdir -p /data/outputs /data/db-backups /data/logs /data/cache \
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
    INKU_LOG_DIR=/data/logs \
    UV_CACHE_DIR=/data/cache

EXPOSE 8100
CMD ["inku-server"]
