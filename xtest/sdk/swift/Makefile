# Makefile for building OpenTDFKitCLI for xtest (macOS / Swift toolchain required)

MAKEFILE_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
VERSIONS ?= $(shell find "$(MAKEFILE_DIR)/src" -mindepth 1 -maxdepth 1 \( -type d -o -type l \) -not -name "*.git" -exec basename {} \; 2>/dev/null)

.PHONY: all build clean help

all: build

build:
	@if [ -z "$(strip $(VERSIONS))" ]; then \
		echo "No versions in sdk/swift/src — checkout with otdf-sdk-mgr first."; \
		exit 1; \
	fi
	@for version in $(VERSIONS); do \
		echo "Building OpenTDFKitCLI for $$version"; \
		SRC="$(MAKEFILE_DIR)/src/$$version"; \
		DIST="$(MAKEFILE_DIR)/dist/$$version"; \
		mkdir -p "$$DIST"; \
		cp "$(MAKEFILE_DIR)/cli.sh" "$$DIST/cli.sh"; \
		chmod +x "$$DIST/cli.sh"; \
		( cd "$$SRC" && swift build -c release --product OpenTDFKitCLI ) || { \
			echo "swift build failed for $$version"; exit 1; \
		}; \
		BIN=$$(cd "$$SRC" && swift build -c release --product OpenTDFKitCLI --show-bin-path)/OpenTDFKitCLI; \
		cp "$$BIN" "$$DIST/OpenTDFKitCLI"; \
		chmod +x "$$DIST/OpenTDFKitCLI"; \
		echo "Installed: $$DIST/OpenTDFKitCLI"; \
	done

clean:
	@for version in $(VERSIONS); do rm -rf "$(MAKEFILE_DIR)/dist/$$version"; done

help:
	@echo "swift SDK Makefile — builds OpenTDFKitCLI (requires Swift on macOS)"
