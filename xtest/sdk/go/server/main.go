package main

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/gorilla/mux"
	"github.com/opentdf/platform/sdk"
)

type Server struct {
	router     *mux.Router
	httpServer *http.Server
	sdkClient  *sdk.SDK
	port       string
}

func NewServer(platformEndpoint string, port string) (*Server, error) {
	// Initialize SDK client with platform endpoint
	sdkClient, err := sdk.New(platformEndpoint)
	if err != nil {
		return nil, fmt.Errorf("failed to create SDK client: %w", err)
	}

	s := &Server{
		router:    mux.NewRouter(),
		sdkClient: sdkClient,
		port:      port,
	}

	s.setupRoutes()
	return s, nil
}

func (s *Server) setupRoutes() {
	// Health check endpoint
	s.router.HandleFunc("/healthz", s.handleHealth).Methods("GET")
	
	// Encryption/Decryption endpoints
	s.router.HandleFunc("/api/encrypt", s.handleEncrypt).Methods("POST")
	s.router.HandleFunc("/api/decrypt", s.handleDecrypt).Methods("POST")
	
	// Policy management endpoints - using SDK's gRPC clients directly
	s.router.HandleFunc("/api/namespaces/list", s.handleNamespaceList).Methods("GET")
	s.router.HandleFunc("/api/namespaces/create", s.handleNamespaceCreate).Methods("POST")
	s.router.HandleFunc("/api/attributes/create", s.handleAttributeCreate).Methods("POST")
	s.router.HandleFunc("/api/attributes/list", s.handleAttributeList).Methods("GET")
	
	// Add logging middleware
	s.router.Use(loggingMiddleware)
}

func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{
		"status": "healthy",
		"sdk":    "github.com/opentdf/platform/sdk",
		"type":   "go",
	})
}

func (s *Server) handleEncrypt(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Data       string   `json:"data"`       // Base64 encoded
		Attributes []string `json:"attributes"` // Attribute FQNs
		Format     string   `json:"format"`     // "nano" or "ztdf"
	}

	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}

	// Decode the base64 data
	plainData, err := base64.StdEncoding.DecodeString(req.Data)
	if err != nil {
		http.Error(w, fmt.Sprintf("Failed to decode base64 data: %v", err), http.StatusBadRequest)
		return
	}

	// Create a reader for the plain data
	reader := bytes.NewReader(plainData)
	
	// Create a buffer to write the TDF
	var tdfBuffer bytes.Buffer

	// Set TDF options based on attributes
	tdfOptions := []sdk.TDFOption{}
	if len(req.Attributes) > 0 {
		tdfOptions = append(tdfOptions, sdk.WithDataAttributes(req.Attributes...))
	}

	// Create TDF (encrypt)
	_, err = s.sdkClient.CreateTDF(&tdfBuffer, reader, tdfOptions...)
	if err != nil {
		http.Error(w, fmt.Sprintf("Failed to encrypt: %v", err), http.StatusInternalServerError)
		return
	}

	// Encode the TDF as base64
	encrypted := base64.StdEncoding.EncodeToString(tdfBuffer.Bytes())

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"encrypted": encrypted,
		"format":    req.Format,
	})
}

func (s *Server) handleDecrypt(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Data string `json:"data"` // Base64 encoded TDF
	}

	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}

	// Decode the base64 TDF
	tdfData, err := base64.StdEncoding.DecodeString(req.Data)
	if err != nil {
		http.Error(w, fmt.Sprintf("Failed to decode base64 TDF: %v", err), http.StatusBadRequest)
		return
	}

	// Create a reader for the TDF data
	tdfReader := bytes.NewReader(tdfData)

	// Load the TDF
	reader, err := s.sdkClient.LoadTDF(tdfReader)
	if err != nil {
		http.Error(w, fmt.Sprintf("Failed to load TDF: %v", err), http.StatusInternalServerError)
		return
	}

	// Read the decrypted data
	var decryptedBuffer bytes.Buffer
	_, err = decryptedBuffer.ReadFrom(reader)
	if err != nil {
		http.Error(w, fmt.Sprintf("Failed to decrypt: %v", err), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"decrypted": decryptedBuffer.String(),
	})
}

func (s *Server) handleNamespaceList(w http.ResponseWriter, r *http.Request) {
	// For now, return empty list - can be implemented with SDK's Namespaces gRPC client
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode([]interface{}{})
}

func (s *Server) handleNamespaceCreate(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Name string `json:"name"`
	}

	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}

	// For now, return success - can be implemented with SDK's Namespaces gRPC client
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"id":   "mock-namespace-id",
		"name": req.Name,
	})
}

func (s *Server) handleAttributeCreate(w http.ResponseWriter, r *http.Request) {
	var req struct {
		NamespaceID string   `json:"namespace_id"`
		Name        string   `json:"name"`
		Rule        string   `json:"rule"`
		Values      []string `json:"values"`
	}

	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}

	// For now, return success - can be implemented with SDK's Attributes gRPC client
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"id":           "mock-attribute-id",
		"namespace_id": req.NamespaceID,
		"name":         req.Name,
		"rule":         req.Rule,
		"values":       req.Values,
	})
}

func (s *Server) handleAttributeList(w http.ResponseWriter, r *http.Request) {
	// For now, return empty list - can be implemented with SDK's Attributes gRPC client
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode([]interface{}{})
}

func (s *Server) Start() error {
	s.httpServer = &http.Server{
		Addr:         ":" + s.port,
		Handler:      s.router,
		ReadTimeout:  15 * time.Second,
		WriteTimeout: 15 * time.Second,
		IdleTimeout:  60 * time.Second,
	}

	log.Printf("Go SDK server starting on port %s", s.port)
	
	// Start server and block
	if err := s.httpServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		return fmt.Errorf("failed to start server: %w", err)
	}
	return nil
}

func (s *Server) StartWithGracefulShutdown() error {
	s.httpServer = &http.Server{
		Addr:         ":" + s.port,
		Handler:      s.router,
		ReadTimeout:  15 * time.Second,
		WriteTimeout: 15 * time.Second,
		IdleTimeout:  60 * time.Second,
	}

	// Start server in a goroutine
	go func() {
		log.Printf("Go SDK server starting on port %s", s.port)
		if err := s.httpServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("Failed to start server: %v", err)
		}
	}()

	// Wait for interrupt signal to gracefully shutdown the server
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit

	log.Println("Shutting down server...")

	// Graceful shutdown with timeout
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	if err := s.httpServer.Shutdown(ctx); err != nil {
		return fmt.Errorf("server forced to shutdown: %w", err)
	}

	log.Println("Server shutdown complete")
	return nil
}

func loggingMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		next.ServeHTTP(w, r)
		log.Printf("%s %s %v", r.Method, r.URL.Path, time.Since(start))
	})
}

func main() {
	var (
		port             string
		platformEndpoint string
		daemonize        bool
	)

	flag.StringVar(&port, "port", "8091", "Port to run the Go SDK server on")
	flag.StringVar(&platformEndpoint, "platform", "http://localhost:8080", "Platform service endpoint")
	flag.BoolVar(&daemonize, "daemonize", false, "Run in background mode")
	flag.Parse()

	// Override with environment variables if set
	if envPort := os.Getenv("GO_SDK_PORT"); envPort != "" {
		port = envPort
	}
	if envPlatform := os.Getenv("PLATFORM_ENDPOINT"); envPlatform != "" {
		platformEndpoint = envPlatform
	}

	server, err := NewServer(platformEndpoint, port)
	if err != nil {
		log.Fatalf("Failed to create server: %v", err)
	}

	if daemonize {
		// For run.py - just start the server without signal handling
		if err := server.Start(); err != nil {
			log.Fatalf("Server error: %v", err)
		}
	} else {
		// For interactive use - handle signals gracefully
		if err := server.StartWithGracefulShutdown(); err != nil {
			log.Fatalf("Server error: %v", err)
		}
	}
}