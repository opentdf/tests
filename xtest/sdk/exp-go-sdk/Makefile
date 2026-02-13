.PHONY: all clean

all: dist/main/cli.sh dist/main/exp-go-sdk

dist/main/exp-go-sdk: main.go go.mod go.sum
	mkdir -p dist/main
	go build -o dist/main/exp-go-sdk .

dist/main/cli.sh: cli.sh
	mkdir -p dist/main
	cp cli.sh dist/main/cli.sh
	chmod +x dist/main/cli.sh

clean:
	rm -rf dist
