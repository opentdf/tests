# Makefile

MAKEFILE_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))

# Dynamically set VERSIONS to the names of all directories in the src folder if not provided in environment
VERSIONS ?= $(shell find ./src -mindepth 1 -maxdepth 1 -type d -not -name "*.git" -exec basename {} \;)

# Fail if no versions are found
ifeq ($(strip $(VERSIONS)),)
$(error No versions found in the sdk/go/src directory)
endif

# Targets
.PHONY: all build clean

all: build
	@echo "Setup go sdk clis for versions: $(VERSIONS)"

build:
	@echo "Building binaries for versions: $(VERSIONS)"
	@for version in $(VERSIONS); do \
		echo "Building binary for $$version"; \
		cd $(MAKEFILE_DIR)/src/$$version && \
		go build -o $(MAKEFILE_DIR)/binary-$$version . || { \
			echo "Error: Go build failed for $$version"; \
			exit 1; \
		}; \
		echo "Copying binary and shell scripts to dist/$$version"; \
		mkdir -p $(MAKEFILE_DIR)/dist/$$version; \
		mv $(MAKEFILE_DIR)/binary-$$version $(MAKEFILE_DIR)/dist/$$version/otdfctl || { \
			echo "Error: Failed to copy binary for $$version"; \
			exit 2; \
		}; \
		cp $(MAKEFILE_DIR)/cli.sh $(MAKEFILE_DIR)/dist/$$version/ || { \
			echo "Error: Failed to copy cli.sh for $$version"; \
			exit 3; \
		}; \
		cp $(MAKEFILE_DIR)/otdfctl.sh $(MAKEFILE_DIR)/dist/$$version/ || { \
			echo "Error: Failed to copy otdfctl.sh for $$version"; \
			exit 3; \
		}; \
		cp $(MAKEFILE_DIR)/opentdfctl.yaml $(MAKEFILE_DIR)/dist/$$version/ || { \
			echo "Error: Failed to copy opentdfctl.yaml for $$version"; \
			exit 3; \
		}; \
	done
	@echo "All binaries built successfully"

clean:
	@echo "Cleaning up binaries"
	@for version in $(VERSIONS); do \
		echo "Removing binary for $$version"; \
		rm -f $(MAKEFILE_DIR)/binary-$$version; \
	done
	@rm -f $(MAKEFILE_DIR)/dist
	@echo "Cleanup complete"
