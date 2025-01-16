# Makefile

# Default paths to the sdk directories, can be overridden by setting the environment variables
JS_DIR ?= ../../../web-sdk
PLATFORM_DIR ?= ../../../platform
OTDFCTL_DIR ?= ../../../otdfctl
JAVA_DIR ?= ../../../java-sdk

JS_DIR_ABS := $(abspath $(JS_DIR))
PLATFORM_DIR_ABS := $(abspath $(PLATFORM_DIR))
OTDFCTL_DIR_ABS := $(abspath $(OTDFCTL_DIR))
JAVA_DIR_ABS := $(abspath $(JAVA_DIR))

MAKEFILE_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))

# Targets
.PHONY: all js go java

all: js go java
	@echo "Setup all sdk clis"

js:
	@echo "Building web-sdk cli..."
	@cd $(JS_DIR_ABS) && make clean && make cli
	@echo "Installing web-sdk cli in xtest"
	@cd $(JS_DIR_ABS)/cli && \
	CLI_NAME=$$(npm pkg get name | tr -d \") && \
	CLI_VERSION=$$(npm pkg get version | tr -d \") && \
	CLI_PATH=cli/$$(echo "$$CLI_NAME" | tr -d @ | sed s1/1-1)-$$CLI_VERSION.tgz &&\
	cd $(MAKEFILE_DIR)/.. && \
	npm un @opentdf/cli || true && \
	npm ci && \
	npm i $(JS_DIR_ABS)/$$CLI_PATH && \
	npm list
	@echo "web-sdk cli installed successfully."
	
go:
	@echo "Replacing otdfctl go.mod packages..."
	@cd $(OTDFCTL_DIR_ABS) && \
	for m in lib/fixtures lib/ocrypto protocol/go sdk; do \
		go mod edit -replace github.com/opentdf/platform/$$m=$(PLATFORM_DIR_ABS)/$$m; \
	done && \
	go mod tidy	
	@echo "Building otdfctl"
	@cd $(OTDFCTL_DIR_ABS) && go build .
	@echo "Moving otdfctl to xtest"
	cp $(OTDFCTL_DIR_ABS)/otdfctl $(MAKEFILE_DIR)/go/otdfctl
	@echo "otdfctl setup successfully"
	
java:
	@echo "Building Java SDK cli..."
	@cd $(JAVA_DIR_ABS) && mvn --batch-mode clean install -DskipTests
	@echo "Moving Java cli to xtest"
	@cp $(JAVA_DIR_ABS)/cmdline/target/cmdline.jar $(MAKEFILE_DIR)/java/cmdline.jar
	@echo "Java SDK cli setup successfully"