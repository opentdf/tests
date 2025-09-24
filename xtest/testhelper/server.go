package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/gorilla/mux"
)

type Server struct {
	router     *mux.Router
	httpServer *http.Server
	client     *PolicyClient
}

func NewServer(platformEndpoint string) (*Server, error) {
	client, err := NewPolicyClient(platformEndpoint)
	if err != nil {
		return nil, fmt.Errorf("failed to create policy client: %w", err)
	}

	s := &Server{
		router: mux.NewRouter(),
		client: client,
	}

	s.setupRoutes()
	return s, nil
}

func (s *Server) setupRoutes() {
	// Health check endpoint
	s.router.HandleFunc("/healthz", s.handleHealth).Methods("GET")

	// KAS Registry endpoints
	s.router.HandleFunc("/api/kas-registry/list", s.handleKasRegistryList).Methods("GET")
	s.router.HandleFunc("/api/kas-registry/create", s.handleKasRegistryCreate).Methods("POST")
	s.router.HandleFunc("/api/kas-registry/keys/list", s.handleKasRegistryKeysList).Methods("GET")
	s.router.HandleFunc("/api/kas-registry/keys/create", s.handleKasRegistryKeyCreate).Methods("POST")

	// Namespace endpoints
	s.router.HandleFunc("/api/namespaces/list", s.handleNamespaceList).Methods("GET")
	s.router.HandleFunc("/api/namespaces/create", s.handleNamespaceCreate).Methods("POST")

	// Attribute endpoints
	s.router.HandleFunc("/api/attributes/create", s.handleAttributeCreate).Methods("POST")
	s.router.HandleFunc("/api/attributes/namespace/key/assign", s.handleNamespaceKeyAssign).Methods("POST")
	s.router.HandleFunc("/api/attributes/key/assign", s.handleAttributeKeyAssign).Methods("POST")
	s.router.HandleFunc("/api/attributes/value/key/assign", s.handleValueKeyAssign).Methods("POST")
	s.router.HandleFunc("/api/attributes/namespace/key/unassign", s.handleNamespaceKeyUnassign).Methods("POST")
	s.router.HandleFunc("/api/attributes/key/unassign", s.handleAttributeKeyUnassign).Methods("POST")
	s.router.HandleFunc("/api/attributes/value/key/unassign", s.handleValueKeyUnassign).Methods("POST")

	// Subject Condition Set endpoints
	s.router.HandleFunc("/api/subject-condition-sets/create", s.handleSubjectConditionSetCreate).Methods("POST")
	s.router.HandleFunc("/api/subject-mappings/create", s.handleSubjectMappingCreate).Methods("POST")

	// Add middleware for logging
	s.router.Use(loggingMiddleware)
}

func (s *Server) Start(port string) error {
	s.httpServer = &http.Server{
		Addr:         ":" + port,
		Handler:      s.router,
		ReadTimeout:  15 * time.Second,
		WriteTimeout: 15 * time.Second,
		IdleTimeout:  60 * time.Second,
	}

	log.Printf("Test helper server starting on port %s", port)
	
	// Start server and block
	if err := s.httpServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		return fmt.Errorf("failed to start server: %w", err)
	}
	return nil
}

func (s *Server) StartWithGracefulShutdown(port string) error {
	s.httpServer = &http.Server{
		Addr:         ":" + port,
		Handler:      s.router,
		ReadTimeout:  15 * time.Second,
		WriteTimeout: 15 * time.Second,
		IdleTimeout:  60 * time.Second,
	}

	// Start server in a goroutine
	go func() {
		log.Printf("Test helper server starting on port %s", port)
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

func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "healthy"})
}

func loggingMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		next.ServeHTTP(w, r)
		log.Printf("%s %s %v", r.Method, r.URL.Path, time.Since(start))
	})
}

func respondWithError(w http.ResponseWriter, code int, message string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	json.NewEncoder(w).Encode(map[string]string{"error": message})
}

func respondWithJSON(w http.ResponseWriter, code int, payload interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	if err := json.NewEncoder(w).Encode(payload); err != nil {
		log.Printf("Error encoding response: %v", err)
	}
}