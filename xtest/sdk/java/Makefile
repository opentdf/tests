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
	@echo "Setup java js sdk clis for versions: $(VERSIONS)"

build:
	@echo "Building java sdk and commandline for versions: $(VERSIONS)"
	@for version in $(VERSIONS); do \
		echo "Building binary for $$version"; \
		cd ./src/$$version && mvn --batch-mode clean install -DskipTests || exit 1; \
		echo "Copying cmdline.jar and cli.sh to dist/$$version"; \
		mkdir -p $(MAKEFILE_DIR)/dist/$$version; \
		cp $(MAKEFILE_DIR)/src/$$version/cmdline/target/cmdline.jar $(MAKEFILE_DIR)/dist/$$version/cmdline.jar || exit 2; \
		cp $(MAKEFILE_DIR)/cli.sh $(MAKEFILE_DIR)/dist/$$version/ || exit 3; \
	done
	@echo "All binaries built successfully"

clean:
	@echo "Cleaning up binaries"
	@for version in $(VERSIONS); do \
		echo "Removing dist for $$version"; \
		rm -rf $(MAKEFILE_DIR)/dist/$$version; \
	done
	@echo "Cleanup complete"
