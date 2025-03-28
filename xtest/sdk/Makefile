# Makefile

# Targets
.PHONY: all js go java

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
