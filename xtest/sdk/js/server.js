#!/usr/bin/env node

/**
 * Test Helper HTTP Server for JavaScript SDK
 * 
 * This server provides the same HTTP API as the Go test helper server
 * but uses the JavaScript SDK directly instead of subprocess calls.
 * This dramatically improves performance for JavaScript-based tests.
 */

import express from 'express';
import bodyParser from 'body-parser';
import morgan from 'morgan';
import { OpenTDF, AuthProviders } from '@opentdf/sdk';
import fetch from 'node-fetch';

const app = express();
const PORT = process.env.TESTHELPER_PORT || 8090;
const PLATFORM_ENDPOINT = process.env.PLATFORM_ENDPOINT || 'http://localhost:8080';
const OIDC_ENDPOINT = process.env.OIDC_ENDPOINT || 'http://localhost:8888/auth';

// Default client credentials for testing
const CLIENT_ID = process.env.CLIENT_ID || 'opentdf';
const CLIENT_SECRET = process.env.CLIENT_SECRET || 'secret';

// Middleware
app.use(bodyParser.json());
app.use(morgan('combined'));

// Create authenticated client
let authProvider;
let platformClient;

async function initializeClient() {
  try {
    authProvider = await AuthProviders.clientSecretAuthProvider({
      clientId: CLIENT_ID,
      clientSecret: CLIENT_SECRET,
      oidcOrigin: OIDC_ENDPOINT,
      exchange: 'client',
    });

    // Initialize platform client for policy operations
    platformClient = {
      authProvider,
      platformEndpoint: PLATFORM_ENDPOINT,
      
      // Helper method to make authenticated requests to platform
      async makeRequest(path, options = {}) {
        const authHeader = await authProvider.withCreds();
        const response = await fetch(`${PLATFORM_ENDPOINT}${path}`, {
          ...options,
          headers: {
            ...options.headers,
            ...authHeader.headers,
            'Content-Type': 'application/json',
          },
        });
        
        if (!response.ok) {
          const error = await response.text();
          throw new Error(`Platform request failed: ${response.status} - ${error}`);
        }
        
        return response.json();
      }
    };

    console.log('Platform client initialized successfully');
  } catch (error) {
    console.error('Failed to initialize platform client:', error);
    throw error;
  }
}

// Health check endpoint
app.get('/healthz', (req, res) => {
  res.json({ status: 'healthy', sdk: '@opentdf/sdk' });
});

// KAS Registry endpoints
app.get('/api/kas-registry/list', async (req, res) => {
  try {
    const result = await platformClient.makeRequest('/api/kas-registry/v2/kas-registries');
    res.json(result.kas_registries || []);
  } catch (error) {
    console.error('Error listing KAS registries:', error);
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/kas-registry/create', async (req, res) => {
  try {
    const { uri, public_keys } = req.body;
    const body = { uri };
    if (public_keys) {
      body.public_keys = JSON.parse(public_keys);
    }
    
    const result = await platformClient.makeRequest('/api/kas-registry/v2/kas-registries', {
      method: 'POST',
      body: JSON.stringify(body),
    });
    res.status(201).json(result);
  } catch (error) {
    console.error('Error creating KAS registry:', error);
    res.status(500).json({ error: error.message });
  }
});

app.get('/api/kas-registry/keys/list', async (req, res) => {
  try {
    const kasUri = req.query.kas;
    if (!kasUri) {
      return res.status(400).json({ error: 'kas parameter is required' });
    }
    
    // Find KAS ID by URI
    const registries = await platformClient.makeRequest('/api/kas-registry/v2/kas-registries');
    const kas = registries.kas_registries?.find(r => r.uri === kasUri);
    if (!kas) {
      return res.status(404).json({ error: 'KAS not found' });
    }
    
    const result = await platformClient.makeRequest(`/api/kas-registry/v2/kas-registries/${kas.id}/keys`);
    res.json(result.keys || []);
  } catch (error) {
    console.error('Error listing KAS keys:', error);
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/kas-registry/keys/create', async (req, res) => {
  try {
    const { kas_uri, public_key_pem, key_id, algorithm } = req.body;
    
    // Find KAS ID by URI
    const registries = await platformClient.makeRequest('/api/kas-registry/v2/kas-registries');
    const kas = registries.kas_registries?.find(r => r.uri === kas_uri);
    if (!kas) {
      return res.status(404).json({ error: 'KAS not found' });
    }
    
    const result = await platformClient.makeRequest(`/api/kas-registry/v2/kas-registries/${kas.id}/keys`, {
      method: 'POST',
      body: JSON.stringify({
        public_key_pem: Buffer.from(public_key_pem, 'base64').toString(),
        key_id,
        algorithm,
      }),
    });
    res.status(201).json(result);
  } catch (error) {
    console.error('Error creating KAS key:', error);
    res.status(500).json({ error: error.message });
  }
});

// Namespace endpoints
app.get('/api/namespaces/list', async (req, res) => {
  try {
    const result = await platformClient.makeRequest('/api/attributes/v2/namespaces');
    res.json(result.namespaces || []);
  } catch (error) {
    console.error('Error listing namespaces:', error);
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/namespaces/create', async (req, res) => {
  try {
    const { name } = req.body;
    const result = await platformClient.makeRequest('/api/attributes/v2/namespaces', {
      method: 'POST',
      body: JSON.stringify({ name }),
    });
    res.status(201).json(result);
  } catch (error) {
    console.error('Error creating namespace:', error);
    res.status(500).json({ error: error.message });
  }
});

// Attribute endpoints
app.post('/api/attributes/create', async (req, res) => {
  try {
    const { namespace_id, name, rule, values } = req.body;
    const result = await platformClient.makeRequest('/api/attributes/v2/attributes', {
      method: 'POST',
      body: JSON.stringify({
        namespace_id,
        name,
        rule,
        values: values || [],
      }),
    });
    res.status(201).json(result);
  } catch (error) {
    console.error('Error creating attribute:', error);
    res.status(500).json({ error: error.message });
  }
});

// Key assignment endpoints
app.post('/api/attributes/namespace/key/assign', async (req, res) => {
  try {
    const { key_id, namespace_id } = req.body;
    const result = await platformClient.makeRequest(`/api/attributes/v2/namespaces/${namespace_id}/keys/${key_id}`, {
      method: 'POST',
    });
    res.json(result);
  } catch (error) {
    console.error('Error assigning namespace key:', error);
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/attributes/key/assign', async (req, res) => {
  try {
    const { key_id, attribute_id } = req.body;
    const result = await platformClient.makeRequest(`/api/attributes/v2/attributes/${attribute_id}/keys/${key_id}`, {
      method: 'POST',
    });
    res.json(result);
  } catch (error) {
    console.error('Error assigning attribute key:', error);
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/attributes/value/key/assign', async (req, res) => {
  try {
    const { key_id, value_id } = req.body;
    const result = await platformClient.makeRequest(`/api/attributes/v2/values/${value_id}/keys/${key_id}`, {
      method: 'POST',
    });
    res.json(result);
  } catch (error) {
    console.error('Error assigning value key:', error);
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/attributes/namespace/key/unassign', async (req, res) => {
  try {
    const { key_id, namespace_id } = req.body;
    const result = await platformClient.makeRequest(`/api/attributes/v2/namespaces/${namespace_id}/keys/${key_id}`, {
      method: 'DELETE',
    });
    res.json(result);
  } catch (error) {
    console.error('Error unassigning namespace key:', error);
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/attributes/key/unassign', async (req, res) => {
  try {
    const { key_id, attribute_id } = req.body;
    const result = await platformClient.makeRequest(`/api/attributes/v2/attributes/${attribute_id}/keys/${key_id}`, {
      method: 'DELETE',
    });
    res.json(result);
  } catch (error) {
    console.error('Error unassigning attribute key:', error);
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/attributes/value/key/unassign', async (req, res) => {
  try {
    const { key_id, value_id } = req.body;
    const result = await platformClient.makeRequest(`/api/attributes/v2/values/${value_id}/keys/${key_id}`, {
      method: 'DELETE',
    });
    res.json(result);
  } catch (error) {
    console.error('Error unassigning value key:', error);
    res.status(500).json({ error: error.message });
  }
});

// Subject Condition Set endpoints
app.post('/api/subject-condition-sets/create', async (req, res) => {
  try {
    const { subject_sets } = req.body;
    const result = await platformClient.makeRequest('/api/entitlements/v2/subject-condition-sets', {
      method: 'POST',
      body: JSON.stringify({
        subject_sets: JSON.parse(subject_sets),
      }),
    });
    res.status(201).json(result);
  } catch (error) {
    console.error('Error creating subject condition set:', error);
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/subject-mappings/create', async (req, res) => {
  try {
    const { attribute_value_id, subject_condition_set_id, action = 'read' } = req.body;
    const result = await platformClient.makeRequest('/api/entitlements/v2/subject-mappings', {
      method: 'POST',
      body: JSON.stringify({
        attribute_value_id,
        subject_condition_set_id,
        actions: [{ action }],
      }),
    });
    res.status(201).json(result);
  } catch (error) {
    console.error('Error creating subject mapping:', error);
    res.status(500).json({ error: error.message });
  }
});

// Encryption/Decryption endpoints (bonus - using SDK directly)
app.post('/api/encrypt', async (req, res) => {
  try {
    const { data, attributes, format = 'ztdf' } = req.body;
    
    const client = new OpenTDF({
      authProvider,
      kasEndpoint: `${PLATFORM_ENDPOINT}/kas`,
    });

    const buffer = Buffer.from(data, 'base64');
    const encrypted = await client.encrypt({
      source: buffer,
      attributes: attributes || [],
      format,
    });

    res.json({
      encrypted: Buffer.from(encrypted).toString('base64'),
      format,
    });
  } catch (error) {
    console.error('Error encrypting:', error);
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/decrypt', async (req, res) => {
  try {
    const { data } = req.body;
    
    const client = new OpenTDF({
      authProvider,
      kasEndpoint: `${PLATFORM_ENDPOINT}/kas`,
    });

    const buffer = Buffer.from(data, 'base64');
    const decrypted = await client.decrypt({
      source: buffer,
    });

    res.json({
      decrypted: Buffer.from(decrypted).toString('base64'),
    });
  } catch (error) {
    console.error('Error decrypting:', error);
    res.status(500).json({ error: error.message });
  }
});

// Error handling middleware
app.use((err, req, res, next) => {
  console.error('Error:', err);
  res.status(500).json({ error: err.message });
});

// Handle graceful shutdown
let server;

async function startServer() {
  try {
    await initializeClient();
    
    server = app.listen(PORT, () => {
      console.log(`JavaScript SDK Test Helper Server running on port ${PORT}`);
      console.log(`Platform endpoint: ${PLATFORM_ENDPOINT}`);
      console.log(`OIDC endpoint: ${OIDC_ENDPOINT}`);
    });
  } catch (error) {
    console.error('Failed to start server:', error);
    process.exit(1);
  }
}

function gracefulShutdown() {
  console.log('\nShutting down server...');
  if (server) {
    server.close(() => {
      console.log('Server shutdown complete');
      process.exit(0);
    });
  } else {
    process.exit(0);
  }
}

// Handle termination signals
process.on('SIGTERM', gracefulShutdown);
process.on('SIGINT', gracefulShutdown);

// Parse command line arguments
const args = process.argv.slice(2);
const daemonize = args.includes('--daemonize') || args.includes('-d');

if (daemonize) {
  // For daemon mode, just start the server
  startServer();
} else {
  // For interactive mode, start with signal handling
  startServer();
}

export { app };