SHELL := /bin/bash

export PYTHONDONTWRITEBYTECODE := 1
UV_CACHE_DIR ?= /tmp/inku-uv-cache
UV_PYTHON_INSTALL_DIR ?= $(HOME)/.local/share/uv/python
export UV_CACHE_DIR UV_PYTHON_INSTALL_DIR
PYTEST_ARGS ?=

.PHONY: git-setup test test-server test-cli test-web

test: test-server test-cli test-web

# A custom merge driver lives in clone-local .git/config. Applying the
# repository setup at the test entry point repairs a missed clone setup before
# the next development cycle reaches a merge.
git-setup:
	./scripts/git/setup.sh

# Keep each suite callable from the same repository-root entry point.
test-server: git-setup
	cd server && uv run pytest -q -rs $(PYTEST_ARGS)

test-cli: git-setup
	cd cli && uv run pytest -q -rs $(PYTEST_ARGS)

test-web: git-setup
	cd web && npm run test:unit
