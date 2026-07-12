# Makefile

# Targets
.PHONY: all js go java community rust swift python

all: js go java
	@echo "Setup all official sdk clis"

community: rust swift python
	@echo "Setup all community sdk clis"

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

rust:
	@echo "Building Rust community SDK..."
	@cd rust && make all
	@echo "Rust SDK built successfully"

swift:
	@echo "Building Swift community SDK..."
	@cd swift && make all
	@echo "Swift SDK built successfully"

python:
	@echo "Building Python community SDK..."
	@cd python && make all
	@echo "Python SDK built successfully"
