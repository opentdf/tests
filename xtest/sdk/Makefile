# Makefile

# Targets
.PHONY: any all js go java

any:
	@built_count=0; \
	if [ -d "js/src" ]; then \
		$(MAKE) js && built_count=$$((built_count + 1)) || exit 1; \
	fi; \
	if [ -d "go/src" ]; then \
		$(MAKE) go && built_count=$$((built_count + 1)) || exit 1; \
	fi; \
	if [ -d "java/src" ]; then \
		$(MAKE) java && built_count=$$((built_count + 1)) || exit 1; \
	fi; \
	if [ $$built_count -eq 0 ]; then \
		echo "Error: No SDKs are checked out"; \
		exit 1; \
	fi

all: js go java

js:
	@echo "Building JavaScript SDK..."
	@cd js && make all
	@echo "✓ JavaScript SDK built successfully"

go:
	@echo "Building Go SDK..."
	@cd go && make all
	@echo "✓ Go SDK built successfully"

java:
	@echo "Building Java SDK..."
	@cd java && make all
	@echo "✓ Java SDK built successfully"
