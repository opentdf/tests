package io.opentdf.tests.controller;

import io.opentdf.tests.service.SdkService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.*;

@RestController
@RequestMapping("/api")
public class SdkController {
    
    private static final Logger logger = LoggerFactory.getLogger(SdkController.class);
    
    @Autowired
    private SdkService sdkService;
    
    @GetMapping("/healthz")
    public Map<String, Object> health() {
        Map<String, Object> health = new HashMap<>();
        health.put("status", "healthy");
        health.put("sdk", "io.opentdf.platform.sdk");
        health.put("type", "java");
        return health;
    }
    
    @PostMapping("/encrypt")
    public ResponseEntity<Map<String, Object>> encrypt(@RequestBody Map<String, Object> request) {
        try {
            String dataBase64 = (String) request.get("data");
            List<String> attributes = (List<String>) request.getOrDefault("attributes", new ArrayList<>());
            String format = (String) request.getOrDefault("format", "ztdf");
            
            byte[] data = Base64.getDecoder().decode(dataBase64);
            byte[] encrypted = sdkService.encrypt(data, attributes, format);
            
            Map<String, Object> response = new HashMap<>();
            response.put("encrypted", Base64.getEncoder().encodeToString(encrypted));
            response.put("format", format);
            
            return ResponseEntity.ok(response);
        } catch (Exception e) {
            logger.error("Encryption failed", e);
            Map<String, Object> error = new HashMap<>();
            error.put("error", e.getMessage());
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(error);
        }
    }
    
    @PostMapping("/decrypt")
    public ResponseEntity<Map<String, Object>> decrypt(@RequestBody Map<String, Object> request) {
        try {
            String dataBase64 = (String) request.get("data");
            byte[] tdfData = Base64.getDecoder().decode(dataBase64);
            byte[] decrypted = sdkService.decrypt(tdfData);
            
            Map<String, Object> response = new HashMap<>();
            response.put("decrypted", Base64.getEncoder().encodeToString(decrypted));
            
            return ResponseEntity.ok(response);
        } catch (Exception e) {
            logger.error("Decryption failed", e);
            Map<String, Object> error = new HashMap<>();
            error.put("error", e.getMessage());
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(error);
        }
    }
    
    // Policy management endpoints (simplified - real implementation would use SDK's policy client)
    
    @GetMapping("/namespaces/list")
    public ResponseEntity<List<Map<String, Object>>> listNamespaces() {
        try {
            // TODO: Use SDK's policy client to list namespaces
            List<Map<String, Object>> namespaces = new ArrayList<>();
            return ResponseEntity.ok(namespaces);
        } catch (Exception e) {
            logger.error("Failed to list namespaces", e);
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(null);
        }
    }
    
    @PostMapping("/namespaces/create")
    public ResponseEntity<Map<String, Object>> createNamespace(@RequestBody Map<String, Object> request) {
        try {
            String name = (String) request.get("name");
            
            // TODO: Use SDK's policy client to create namespace
            Map<String, Object> namespace = new HashMap<>();
            namespace.put("id", UUID.randomUUID().toString());
            namespace.put("name", name);
            namespace.put("fqn", "https://" + name);
            
            return ResponseEntity.status(HttpStatus.CREATED).body(namespace);
        } catch (Exception e) {
            logger.error("Failed to create namespace", e);
            Map<String, Object> error = new HashMap<>();
            error.put("error", e.getMessage());
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(error);
        }
    }
    
    @PostMapping("/attributes/create")
    public ResponseEntity<Map<String, Object>> createAttribute(@RequestBody Map<String, Object> request) {
        try {
            String namespaceId = (String) request.get("namespace_id");
            String name = (String) request.get("name");
            String rule = (String) request.getOrDefault("rule", "ANY_OF");
            List<String> values = (List<String>) request.getOrDefault("values", new ArrayList<>());
            
            // TODO: Use SDK's policy client to create attribute
            Map<String, Object> attribute = new HashMap<>();
            attribute.put("id", UUID.randomUUID().toString());
            attribute.put("namespace_id", namespaceId);
            attribute.put("name", name);
            attribute.put("rule", rule);
            attribute.put("values", values);
            
            return ResponseEntity.status(HttpStatus.CREATED).body(attribute);
        } catch (Exception e) {
            logger.error("Failed to create attribute", e);
            Map<String, Object> error = new HashMap<>();
            error.put("error", e.getMessage());
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(error);
        }
    }
    
    @GetMapping("/attributes/list")
    public ResponseEntity<List<Map<String, Object>>> listAttributes(
            @RequestParam(required = false) String namespaceId) {
        try {
            // TODO: Use SDK's policy client to list attributes
            List<Map<String, Object>> attributes = new ArrayList<>();
            return ResponseEntity.ok(attributes);
        } catch (Exception e) {
            logger.error("Failed to list attributes", e);
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(null);
        }
    }
}