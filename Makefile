SHELL := /bin/bash

export PYTHONDONTWRITEBYTECODE := 1
UV_CACHE_DIR ?= /tmp/inku-uv-cache
UV_PYTHON_INSTALL_DIR ?= $(HOME)/.local/share/uv/python
export UV_CACHE_DIR UV_PYTHON_INSTALL_DIR
PYTEST_ARGS ?=

.PHONY: test test-server test-cli test-web

test: test-server test-cli test-web

# Keep each suite callable from the same repository-root entry point.
test-server:
	cd server && uv run pytest -q -rs $(PYTEST_ARGS)

test-cli:
	cd cli && uv run pytest -q -rs $(PYTEST_ARGS)

test-web:
	cd web && npm run test:unit
