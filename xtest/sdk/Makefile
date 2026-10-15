# Makefile

# Targets
.PHONY: all js go java web

all: js go java
	@echo "Setup all sdk clis"

js:
	@echo "Building JavaScript SDK..."
	@cd js && make all
	@echo "JavaScript SDK built successfully"

go:
	@echo "Building Go SDK..."
	@cd go && make all
	@echo "Go SDK built successfully"

java:
	@echo "Building Java SDK..."
	@cd java && make all
	@echo "Java SDK built successfully"

# Not in `all`: staging web downloads a Playwright browser. Builds from the
# same checkouts as js (sdk/js/src).
web:
	@echo "Building headless-browser web SDK flavour..."
	@cd web && make all
	@echo "web SDK flavour built successfully"
