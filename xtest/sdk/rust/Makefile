# Makefile for building the community Rust SDK xtest_cli

MAKEFILE_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
VERSIONS ?= $(shell find "$(MAKEFILE_DIR)/src" -mindepth 1 -maxdepth 1 \( -type d -o -type l \) -not -name "*.git" -exec basename {} \; 2>/dev/null)
CARGO_FEATURES ?= kas-client,cbor

.PHONY: all build clean help

all: build

build:
	@if [ -z "$(strip $(VERSIONS))" ]; then \
		echo "No versions in sdk/rust/src — checkout with otdf-sdk-mgr first."; \
		exit 1; \
	fi
	@for version in $(VERSIONS); do \
		echo "Building xtest_cli for $$version"; \
		SRC="$(MAKEFILE_DIR)/src/$$version"; \
		DIST="$(MAKEFILE_DIR)/dist/$$version"; \
		mkdir -p "$$DIST"; \
		cp "$(MAKEFILE_DIR)/cli.sh" "$$DIST/cli.sh"; \
		chmod +x "$$DIST/cli.sh"; \
		( cd "$$SRC" && cargo build --release --example xtest_cli --features "$(CARGO_FEATURES)" ) || { \
			echo "cargo build failed for $$version"; exit 1; \
		}; \
		cp "$$SRC/target/release/examples/xtest_cli" "$$DIST/xtest_cli"; \
		chmod +x "$$DIST/xtest_cli"; \
		echo "Installed: $$DIST/xtest_cli"; \
	done

clean:
	@for version in $(VERSIONS); do rm -rf "$(MAKEFILE_DIR)/dist/$$version"; done

help:
	@echo "rust SDK Makefile — builds examples/xtest_cli with features: $(CARGO_FEATURES)"
