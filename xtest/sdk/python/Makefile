# Makefile for building the community Python SDK CLI for xtest

MAKEFILE_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))

# Dynamically set VERSIONS from sdk/python/src/* worktrees if not provided
VERSIONS ?= $(shell find "$(MAKEFILE_DIR)/src" -mindepth 1 -maxdepth 1 \( -type d -o -type l \) -not -name "*.git" -exec basename {} \; 2>/dev/null)

.PHONY: all build clean help

all: build
	@echo "Setup python sdk clis for versions: $(VERSIONS)"

build:
	@if [ -z "$(strip $(VERSIONS))" ]; then \
		echo "No versions found in sdk/python/src — checkout with otdf-sdk-mgr first, or link a local tree."; \
		exit 1; \
	fi
	@for version in $(VERSIONS); do \
		echo "Installing otdf-python for $$version"; \
		SRC="$(MAKEFILE_DIR)/src/$$version"; \
		DIST="$(MAKEFILE_DIR)/dist/$$version"; \
		mkdir -p "$$DIST"; \
		cp "$(MAKEFILE_DIR)/cli.sh" "$$DIST/cli.sh"; \
		chmod +x "$$DIST/cli.sh"; \
		if [ -f "$$SRC/packages/otdf-python/pyproject.toml" ]; then \
			echo "  editable install from monorepo packages/"; \
			python3 -m venv "$$DIST/.venv"; \
			"$$DIST/.venv/bin/pip" install -U pip wheel; \
			if [ -f "$$SRC/packages/otdf-python-proto/pyproject.toml" ]; then \
				"$$DIST/.venv/bin/pip" install -e "$$SRC/packages/otdf-python-proto" || true; \
			fi; \
			"$$DIST/.venv/bin/pip" install -e "$$SRC/packages/otdf-python"; \
		elif [ -f "$$SRC/pyproject.toml" ]; then \
			python3 -m venv "$$DIST/.venv"; \
			"$$DIST/.venv/bin/pip" install -U pip wheel; \
			"$$DIST/.venv/bin/pip" install -e "$$SRC"; \
		else \
			echo "Error: no pyproject.toml under $$SRC" >&2; \
			exit 1; \
		fi; \
		ln -sfn .venv/bin/python "$$DIST/otdf-python-python" 2>/dev/null || true; \
		printf '%s\n' '#!/usr/bin/env bash' \
			'exec "$$(cd "$$(dirname "$$0")" && pwd)/.venv/bin/python" -m otdf_python "$$@"' \
			> "$$DIST/otdf-python"; \
		chmod +x "$$DIST/otdf-python"; \
		echo "Installed: $$DIST"; \
	done
	@echo "All python SDK clis built successfully"

clean:
	@for version in $(VERSIONS); do \
		rm -rf "$(MAKEFILE_DIR)/dist/$$version"; \
	done
	@echo "Cleanup complete"

help:
	@echo "python SDK Makefile"
	@echo "  all/build  - install otdf-python into dist/<version>"
	@echo "  clean      - remove dist trees"
