# Makefile

MAKEFILE_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))

# Dynamically set VERSIONS to the names of all directories in the src folder if not provided
VERSIONS ?= $(shell find ./src -mindepth 1 -maxdepth 1 -type d -not -name "*.git" -exec basename {} \;)

# Fail if no versions are found
ifeq ($(strip $(VERSIONS)),)
$(error No versions found in the sdk/js/src directory)
endif

# Targets
.PHONY: all build clean

all: build
	@echo "Setup all js sdk clis for versions: $(VERSIONS)"

build:
	@echo "Building binaries for versions: $(VERSIONS)"
	@for version in $(VERSIONS); do \
		echo "Building binary for $$version"; \
		cd $(MAKEFILE_DIR)/src/$$version && make cli || { \
			echo "Error: Failed to build CLI for $$version"; \
			exit 1; \
		}; \
		echo "Copying cli.sh to dist/$$version"; \
		CLI_NAME=$$(cd $(MAKEFILE_DIR)/src/$$version/cli && npm pkg get name | tr -d \"); \
		CLI_VERSION=$$(cd $(MAKEFILE_DIR)/src/$$version/cli && npm pkg get version | tr -d \"); \
		CLI_PATH=$(MAKEFILE_DIR)/src/$$version/cli/$$(echo "$$CLI_NAME" | tr -d @ | sed s1/1-1)-$$CLI_VERSION.tgz; \
		mkdir -p $(MAKEFILE_DIR)/dist/$$version; \
		cp $(MAKEFILE_DIR)/cli.sh $(MAKEFILE_DIR)/dist/$$version/ || { \
			echo "Error: Failed to copy cli.sh for $$version"; \
			exit 2; \
		}; \
		echo "Installing $$CLI_PATH into dist/$$version"; \
		cd $(MAKEFILE_DIR)/dist/$$version && npm i $$CLI_PATH || { \
			echo "Error: Failed to install CLI package for $$version"; \
			exit 3; \
		}; \
	done
	@echo "All binaries built successfully"

clean:
	@echo "Cleaning up binaries"
	@for version in $(VERSIONS); do \
		echo "Removing dist for $$version"; \
		rm -rf $(MAKEFILE_DIR)/dist/$$version; \
	done
	@echo "Cleanup complete"
