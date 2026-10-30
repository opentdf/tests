# Makefile
#
# Source builds of the `web` SDK flavour. There is no separate web-sdk
# checkout: web and js are the same repository, so this reuses the worktrees
# under ../js/src/ (otdf-sdk-mgr checks them out there for both flavours) and
# packs the library from them.

MAKEFILE_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
JS_SRC := $(MAKEFILE_DIR)../js/src

# Dynamically set VERSIONS to the names of all web-sdk checkouts if not provided
VERSIONS ?= $(shell find "$(JS_SRC)" -mindepth 1 -maxdepth 1 -type d -not -name "*.git" -exec basename {} \; 2>/dev/null)

# Targets
.PHONY: all build clean from-js

all: build
	@echo "Setup web sdk drivers for versions: $(VERSIONS)"

build:
	@if [ -z "$(strip $(VERSIONS))" ]; then \
		echo "Error: No web-sdk checkouts found in the sdk/js/src directory"; \
		exit 1; \
	fi
	@echo "Building web drivers for versions: $(VERSIONS)"
	@for version in $(VERSIONS); do \
		src="$(JS_SRC)/$$version"; \
		lib_version=$$(sed -n 's/^version=//p' "$$src/Makefile"); \
		if [ -z "$$lib_version" ]; then \
			echo "Error: no version= line in $$src/Makefile"; \
			exit 1; \
		fi; \
		echo "Packing @opentdf/sdk $$lib_version from $$src"; \
		$(MAKE) -C "$$src" "lib/opentdf-sdk-$$lib_version.tgz" || { \
			echo "Error: Failed to pack lib for $$version"; \
			exit 2; \
		}; \
		$(MAKEFILE_DIR)stage.sh "$(MAKEFILE_DIR)dist/$$version" "$$src/lib/opentdf-sdk-$$lib_version.tgz" || { \
			echo "Error: Failed to stage web driver for $$version"; \
			exit 3; \
		}; \
	done
	@echo "All web drivers built successfully"

# Stage a web driver for every js version already installed under ../js/dist,
# under the same dist name, so the two flavours run the same library. Source
# builds (a checkout exists under ../js/src/<name>) pack the library from that
# checkout; releases install @opentdf/sdk at the version the name gives, which
# web-sdk releases in lockstep with @opentdf/ctl. CI calls this after building
# the js CLIs.
from-js:
	@found=0; \
	for d in $(MAKEFILE_DIR)../js/dist/*/; do \
		[ -d "$$d" ] || continue; \
		found=1; \
		name=$$(basename "$$d"); \
		if [ -f "$(JS_SRC)/$$name/Makefile" ]; then \
			$(MAKE) -C $(MAKEFILE_DIR) build VERSIONS="$$name" || exit 1; \
		else \
			$(MAKEFILE_DIR)stage.sh "$(MAKEFILE_DIR)dist/$$name" "@opentdf/sdk@$${name#v}" || exit 1; \
		fi; \
	done; \
	if [ "$$found" = 0 ]; then \
		echo "Error: no js versions installed under ../js/dist"; \
		exit 1; \
	fi

clean:
	@echo "Cleaning up web drivers"
	@for version in $(VERSIONS); do \
		echo "Removing dist for $$version"; \
		rm -rf $(MAKEFILE_DIR)dist/$$version; \
	done
	@echo "Cleanup complete"
