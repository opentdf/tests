# Makefile

JS_DIR ?= js
OTDFCTL_DIR ?= go
JAVA_DIR ?= java

JS_DIR_ABS := $(abspath $(JS_DIR))
OTDFCTL_DIR_ABS := $(abspath $(OTDFCTL_DIR))
JAVA_DIR_ABS := $(abspath $(JAVA_DIR))

MAKEFILE_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))

# Targets
.PHONY: all js go java

all: js go java
	@echo "Setup all sdk clis"

js:
	@echo "Building JavaScript SDK..."
	@cd $(JS_DIR_ABS) && make all
	@echo "JavaScript SDK built successfully"

go:
	@echo "Building Go SDK..."
	@cd $(OTDFCTL_DIR_ABS) && make all
	@echo "Go SDK built successfully"

java:
	@echo "Building Java SDK..."
	@cd $(JAVA_DIR_ABS) && make all
	@echo "Java SDK built successfully"
