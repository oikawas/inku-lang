# This immutable builder contains Rust 1.95.0, maturin 1.13.3, and CPython 3.12.
# Only the native wheel crosses into the runtime image; Rust and Cargo do not.
FROM ghcr.io/pyo3/maturin@sha256:2519833ac5bf071e02fa231ce368b5b69fac8be1b0774376e3de103f9bed2578 AS native-builder

WORKDIR /build
COPY core/ /build/core/
COPY server/scripts/build_rust_notices.py /build/build_rust_notices.py
RUN cargo fetch --manifest-path /build/core/Cargo.toml --locked \
    && maturin build \
    --manifest-path /build/core/crates/inku-render-python/Cargo.toml \
    --release \
    --locked \
    --compatibility manylinux2014 \
    --out /wheelhouse \
    && python3.12 /build/build_rust_notices.py \
       /build/core/Cargo.lock /wheelhouse/RUST_THIRD_PARTY_NOTICES.txt

# Preserve Ubuntu's security fixes as well as the engine version used by 5173.
# Keep this library isolated from the Debian base's package-managed libraries.
FROM ubuntu:22.04 AS sqlite-library
COPY server/runtime/sqlite.json /opt/inku-sqlite/contract.json
RUN apt-get update \
    && apt-get install -y --no-install-recommends jq \
    && sqlite_package="$(jq -er .ubuntu_package_version /opt/inku-sqlite/contract.json)" \
    && apt-get install -y --no-install-recommends \
       "libsqlite3-0=${sqlite_package}" "libsqlite3-dev=${sqlite_package}" \
    && test "$(dpkg-query -W -f='${Version}' libsqlite3-0)" = "${sqlite_package}" \
    && mkdir -p /opt/inku-sqlite/lib /opt/inku-sqlite/include /opt/inku-sqlite/licenses \
    && cp -a /usr/lib/*-linux-gnu/libsqlite3.so* /opt/inku-sqlite/lib/ \
    && cp /usr/include/sqlite3.h /usr/include/sqlite3ext.h /opt/inku-sqlite/include/ \
    && cp /usr/share/doc/libsqlite3-0/copyright /opt/inku-sqlite/licenses/Ubuntu-libsqlite3-copyright.txt

# A newer header can introduce symbols absent in 3.37.2. Rebuild only CPython's
# unmodified _sqlite3 module with these headers instead of swapping its library
# underneath the stock module. No compiler crosses into the runtime image.
FROM python:3.12.15-slim AS sqlite-module
COPY --from=sqlite-library /opt/inku-sqlite/ /opt/inku-sqlite/
COPY server/scripts/build_sqlite_module.py /tmp/build_sqlite_module.py
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libc6-dev \
    && python /tmp/build_sqlite_module.py

FROM python:3.12.15-slim AS python-runtime
COPY --from=sqlite-module /opt/inku-sqlite/lib/ /opt/inku-sqlite/lib/
COPY --from=sqlite-module /opt/inku-sqlite/licenses/ /opt/inku-sqlite/licenses/
COPY --from=sqlite-module /opt/inku-sqlite/contract.json /opt/inku-sqlite/metadata.json /opt/inku-sqlite/
COPY --from=sqlite-module /usr/local/lib/python3.12/lib-dynload/_sqlite3*.so /usr/local/lib/python3.12/lib-dynload/
COPY server/scripts/check_sqlite_runtime.py /opt/inku-sqlite/check_runtime.py

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_PREFERENCE=only-system \
    UV_PYTHON_DOWNLOADS=never

# libcairo2 was here for cairosvg, which v2.7.10 removed entirely. resvg-py is
# a wheel and needs no OS library of its own, so nothing in the image links
# against cairo any more.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv \
    && python /opt/inku-sqlite/check_runtime.py

FROM python-runtime AS runtime

WORKDIR /app
COPY shared/ /app/shared/
COPY server/ /app/server/
COPY LICENSE /app/LICENSE
COPY --from=native-builder /wheelhouse/RUST_THIRD_PARTY_NOTICES.txt /app/licenses/RUST_THIRD_PARTY_NOTICES.txt
COPY --from=native-builder /wheelhouse/ /tmp/wheelhouse/
RUN cd /app/server \
    && uv sync --frozen --no-dev \
    && uv pip install --python /app/server/.venv/bin/python --no-deps /tmp/wheelhouse/*.whl \
    && /app/server/.venv/bin/python /opt/inku-sqlite/check_runtime.py \
    && rm -rf /tmp/wheelhouse \
    && test -s /app/LICENSE \
    && test -s /app/server/THIRD_PARTY_NOTICES.md \
    && test -s /app/server/src/inku_server/notices/sudachidict-small-20260723.1-LEGAL.txt \
    && test -s /app/licenses/RUST_THIRD_PARTY_NOTICES.txt \
    && test -s /app/server/src/inku_server/fonts/OFL.txt

# Copied after the dependency sync so re-numbering a build does not invalidate it.
# api.py resolves the build number relative to the package: parents[3]/web/BUILD_NUMBER.
# APP_VERSION is read the same way (reference.py and api_core/common.py); without it
# the published image answered /api/info with version "unknown" -- ledger I-327.
COPY web/BUILD_NUMBER /app/web/BUILD_NUMBER
COPY web/APP_VERSION /app/web/APP_VERSION

RUN useradd --create-home --uid 10001 inku \
    && mkdir -p /data/outputs /data/db-backups /data/logs /data/cache /data/chatgpt \
    && chmod 0700 /data/chatgpt \
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
    INKU_CHATGPT_AUTH_DIR=/data/chatgpt \
    UV_CACHE_DIR=/data/cache

EXPOSE 8100
CMD ["inku-server"]
