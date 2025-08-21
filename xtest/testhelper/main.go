package main

import (
	"flag"
	"log"
	"os"
)

func main() {
	var (
		port             string
		platformEndpoint string
		daemonize        bool
	)

	flag.StringVar(&port, "port", "8090", "Port to run the test helper server on")
	flag.StringVar(&platformEndpoint, "platform", "http://localhost:8080", "Platform service endpoint")
	flag.BoolVar(&daemonize, "daemonize", false, "Run in background mode (for run.py)")
	flag.Parse()

	// Override with environment variables if set
	if envPort := os.Getenv("TESTHELPER_PORT"); envPort != "" {
		port = envPort
	}
	if envPlatform := os.Getenv("PLATFORM_ENDPOINT"); envPlatform != "" {
		platformEndpoint = envPlatform
	}

	server, err := NewServer(platformEndpoint)
	if err != nil {
		log.Fatalf("Failed to create server: %v", err)
	}

	if daemonize {
		// For run.py - just start the server without signal handling
		if err := server.Start(port); err != nil {
			log.Fatalf("Server error: %v", err)
		}
	} else {
		// For interactive use - handle signals gracefully
		if err := server.StartWithGracefulShutdown(port); err != nil {
			log.Fatalf("Server error: %v", err)
		}
	}
}