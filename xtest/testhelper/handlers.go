package main

import (
	"encoding/json"
	"net/http"
)

// KAS Registry handlers

func (s *Server) handleKasRegistryList(w http.ResponseWriter, r *http.Request) {
	result, err := s.client.ListKasRegistries(r.Context())
	if err != nil {
		respondWithError(w, http.StatusInternalServerError, err.Error())
		return
	}
	respondWithJSON(w, http.StatusOK, result)
}

func (s *Server) handleKasRegistryCreate(w http.ResponseWriter, r *http.Request) {
	var req struct {
		URI        string `json:"uri"`
		PublicKeys string `json:"public_keys,omitempty"`
	}

	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		respondWithError(w, http.StatusBadRequest, "Invalid request body")
		return
	}

	result, err := s.client.CreateKasRegistry(r.Context(), req.URI, req.PublicKeys)
	if err != nil {
		respondWithError(w, http.StatusInternalServerError, err.Error())
		return
	}
	respondWithJSON(w, http.StatusCreated, result)
}

func (s *Server) handleKasRegistryKeysList(w http.ResponseWriter, r *http.Request) {
	kasURI := r.URL.Query().Get("kas")
	if kasURI == "" {
		respondWithError(w, http.StatusBadRequest, "kas parameter is required")
		return
	}

	result, err := s.client.ListKasRegistryKeys(r.Context(), kasURI)
	if err != nil {
		respondWithError(w, http.StatusInternalServerError, err.Error())
		return
	}
	respondWithJSON(w, http.StatusOK, result)
}

func (s *Server) handleKasRegistryKeyCreate(w http.ResponseWriter, r *http.Request) {
	var req struct {
		KasURI       string `json:"kas_uri"`
		PublicKeyPEM string `json:"public_key_pem"`
		KeyID        string `json:"key_id"`
		Algorithm    string `json:"algorithm"`
	}

	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		respondWithError(w, http.StatusBadRequest, "Invalid request body")
		return
	}

	result, err := s.client.CreateKasRegistryKey(r.Context(), req.KasURI, req.PublicKeyPEM, req.KeyID, req.Algorithm)
	if err != nil {
		respondWithError(w, http.StatusInternalServerError, err.Error())
		return
	}
	respondWithJSON(w, http.StatusCreated, result)
}

// Namespace handlers

func (s *Server) handleNamespaceList(w http.ResponseWriter, r *http.Request) {
	result, err := s.client.ListNamespaces(r.Context())
	if err != nil {
		respondWithError(w, http.StatusInternalServerError, err.Error())
		return
	}
	respondWithJSON(w, http.StatusOK, result)
}

func (s *Server) handleNamespaceCreate(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Name string `json:"name"`
	}

	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		respondWithError(w, http.StatusBadRequest, "Invalid request body")
		return
	}

	result, err := s.client.CreateNamespace(r.Context(), req.Name)
	if err != nil {
		respondWithError(w, http.StatusInternalServerError, err.Error())
		return
	}
	respondWithJSON(w, http.StatusCreated, result)
}

// Attribute handlers

func (s *Server) handleAttributeCreate(w http.ResponseWriter, r *http.Request) {
	var req struct {
		NamespaceID string   `json:"namespace_id"`
		Name        string   `json:"name"`
		Rule        string   `json:"rule"`
		Values      []string `json:"values,omitempty"`
	}

	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		respondWithError(w, http.StatusBadRequest, "Invalid request body")
		return
	}

	result, err := s.client.CreateAttribute(r.Context(), req.NamespaceID, req.Name, req.Rule, req.Values)
	if err != nil {
		respondWithError(w, http.StatusInternalServerError, err.Error())
		return
	}
	respondWithJSON(w, http.StatusCreated, result)
}

// Key assignment handlers

func (s *Server) handleNamespaceKeyAssign(w http.ResponseWriter, r *http.Request) {
	var req struct {
		KeyID       string `json:"key_id"`
		NamespaceID string `json:"namespace_id"`
	}

	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		respondWithError(w, http.StatusBadRequest, "Invalid request body")
		return
	}

	result, err := s.client.AssignNamespaceKey(r.Context(), req.KeyID, req.NamespaceID)
	if err != nil {
		respondWithError(w, http.StatusInternalServerError, err.Error())
		return
	}
	respondWithJSON(w, http.StatusOK, result)
}

func (s *Server) handleAttributeKeyAssign(w http.ResponseWriter, r *http.Request) {
	var req struct {
		KeyID       string `json:"key_id"`
		AttributeID string `json:"attribute_id"`
	}

	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		respondWithError(w, http.StatusBadRequest, "Invalid request body")
		return
	}

	result, err := s.client.AssignAttributeKey(r.Context(), req.KeyID, req.AttributeID)
	if err != nil {
		respondWithError(w, http.StatusInternalServerError, err.Error())
		return
	}
	respondWithJSON(w, http.StatusOK, result)
}

func (s *Server) handleValueKeyAssign(w http.ResponseWriter, r *http.Request) {
	var req struct {
		KeyID   string `json:"key_id"`
		ValueID string `json:"value_id"`
	}

	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		respondWithError(w, http.StatusBadRequest, "Invalid request body")
		return
	}

	result, err := s.client.AssignValueKey(r.Context(), req.KeyID, req.ValueID)
	if err != nil {
		respondWithError(w, http.StatusInternalServerError, err.Error())
		return
	}
	respondWithJSON(w, http.StatusOK, result)
}

func (s *Server) handleNamespaceKeyUnassign(w http.ResponseWriter, r *http.Request) {
	var req struct {
		KeyID       string `json:"key_id"`
		NamespaceID string `json:"namespace_id"`
	}

	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		respondWithError(w, http.StatusBadRequest, "Invalid request body")
		return
	}

	result, err := s.client.UnassignNamespaceKey(r.Context(), req.KeyID, req.NamespaceID)
	if err != nil {
		respondWithError(w, http.StatusInternalServerError, err.Error())
		return
	}
	respondWithJSON(w, http.StatusOK, result)
}

func (s *Server) handleAttributeKeyUnassign(w http.ResponseWriter, r *http.Request) {
	var req struct {
		KeyID       string `json:"key_id"`
		AttributeID string `json:"attribute_id"`
	}

	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		respondWithError(w, http.StatusBadRequest, "Invalid request body")
		return
	}

	result, err := s.client.UnassignAttributeKey(r.Context(), req.KeyID, req.AttributeID)
	if err != nil {
		respondWithError(w, http.StatusInternalServerError, err.Error())
		return
	}
	respondWithJSON(w, http.StatusOK, result)
}

func (s *Server) handleValueKeyUnassign(w http.ResponseWriter, r *http.Request) {
	var req struct {
		KeyID   string `json:"key_id"`
		ValueID string `json:"value_id"`
	}

	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		respondWithError(w, http.StatusBadRequest, "Invalid request body")
		return
	}

	result, err := s.client.UnassignValueKey(r.Context(), req.KeyID, req.ValueID)
	if err != nil {
		respondWithError(w, http.StatusInternalServerError, err.Error())
		return
	}
	respondWithJSON(w, http.StatusOK, result)
}

// Subject Condition Set handlers

func (s *Server) handleSubjectConditionSetCreate(w http.ResponseWriter, r *http.Request) {
	var req struct {
		SubjectSets string `json:"subject_sets"`
	}

	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		respondWithError(w, http.StatusBadRequest, "Invalid request body")
		return
	}

	result, err := s.client.CreateSubjectConditionSet(r.Context(), req.SubjectSets)
	if err != nil {
		respondWithError(w, http.StatusInternalServerError, err.Error())
		return
	}
	respondWithJSON(w, http.StatusCreated, result)
}

func (s *Server) handleSubjectMappingCreate(w http.ResponseWriter, r *http.Request) {
	var req struct {
		AttributeValueID      string `json:"attribute_value_id"`
		SubjectConditionSetID string `json:"subject_condition_set_id"`
		Action                string `json:"action"`
	}

	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		respondWithError(w, http.StatusBadRequest, "Invalid request body")
		return
	}

	// Default action to "read" if not specified
	if req.Action == "" {
		req.Action = "read"
	}

	result, err := s.client.CreateSubjectMapping(r.Context(), req.AttributeValueID, req.SubjectConditionSetID, req.Action)
	if err != nil {
		respondWithError(w, http.StatusInternalServerError, err.Error())
		return
	}
	respondWithJSON(w, http.StatusCreated, result)
}