SHELL := /bin/bash

export PYTHONDONTWRITEBYTECODE := 1
UV_CACHE_DIR ?= /tmp/inku-uv-cache
UV_PYTHON_INSTALL_DIR ?= $(HOME)/.local/share/uv/python
export UV_CACHE_DIR UV_PYTHON_INSTALL_DIR
PYTEST_ARGS ?=
RUST := ./scripts/rust-toolchain.sh

.PHONY: git-setup test test-server test-cli test-web rust-fmt rust-check rust-test rust-clippy rust-toolchain-test

test: test-server test-cli test-web

# A custom merge driver lives in clone-local .git/config. Applying the
# repository setup at the test entry point repairs a missed clone setup before
# the next development cycle reaches a merge.
git-setup:
	./scripts/git/setup.sh

# Keep each suite callable from the same repository-root entry point.
# The Server keeps the separately deployed native wheel out of its dependency
# graph, so its suite builds the wheel from this checkout on every run and
# injects it. `uv run --with <crate dir>` reuses a cached build after the Rust
# sources change; a wheel built here cannot be stale. `rustup run` keeps the
# pinned toolchain even where another cargo comes first on PATH.
RUST_CHANNEL := $(shell sed -n 's/^channel = "\(.*\)"/\1/p' core/rust-toolchain.toml)
NATIVE_WHEEL_DIR := $(CURDIR)/.native-wheel

test-server: git-setup
	rm -rf "$(NATIVE_WHEEL_DIR)"
	rustup run $(RUST_CHANNEL) uv build --wheel core/crates/inku-render-python -o "$(NATIVE_WHEEL_DIR)"
	cd server && uv run --with "$$(ls "$(NATIVE_WHEEL_DIR)"/*.whl)" pytest -q -rs $(PYTEST_ARGS)

test-cli: git-setup
	cd cli && uv run pytest -q -rs $(PYTEST_ARGS)

test-web: git-setup
	cd web && npm run test:unit

# Rust commands always enter through the pinned rustup toolchain guard.  The
# wrapper overrides a Homebrew-first PATH and refuses non-rustup tool paths.
rust-fmt:
	$(RUST) fmt --all --check

rust-check:
	$(RUST) check --workspace --locked

rust-test:
	$(RUST) test --workspace --locked

rust-clippy:
	$(RUST) clippy --workspace --all-targets --locked -- -D warnings

rust-toolchain-test:
	./scripts/test_rust_toolchain.sh
