#!/usr/bin/env node

import express from 'express';
import bodyParser from 'body-parser';
import morgan from 'morgan';
import { PolicyClient } from './client.js';

const app = express();
const PORT = process.env.TESTHELPER_PORT || 8090;
const PLATFORM_ENDPOINT = process.env.PLATFORM_ENDPOINT || 'http://localhost:8080';

// Middleware
app.use(bodyParser.json());
app.use(morgan('combined'));

// Initialize policy client
const policyClient = new PolicyClient(PLATFORM_ENDPOINT);

// Health check endpoint
app.get('/healthz', (req, res) => {
  res.json({ status: 'healthy' });
});

// KAS Registry endpoints
app.get('/api/kas-registry/list', async (req, res) => {
  try {
    const result = await policyClient.listKasRegistries();
    res.json(result);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/kas-registry/create', async (req, res) => {
  try {
    const { uri, public_keys } = req.body;
    const result = await policyClient.createKasRegistry(uri, public_keys);
    res.status(201).json(result);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.get('/api/kas-registry/keys/list', async (req, res) => {
  try {
    const kasUri = req.query.kas;
    if (!kasUri) {
      return res.status(400).json({ error: 'kas parameter is required' });
    }
    const result = await policyClient.listKasRegistryKeys(kasUri);
    res.json(result);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/kas-registry/keys/create', async (req, res) => {
  try {
    const { kas_uri, public_key_pem, key_id, algorithm } = req.body;
    const result = await policyClient.createKasRegistryKey(kas_uri, public_key_pem, key_id, algorithm);
    res.status(201).json(result);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Namespace endpoints
app.get('/api/namespaces/list', async (req, res) => {
  try {
    const result = await policyClient.listNamespaces();
    res.json(result);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/namespaces/create', async (req, res) => {
  try {
    const { name } = req.body;
    const result = await policyClient.createNamespace(name);
    res.status(201).json(result);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Attribute endpoints
app.post('/api/attributes/create', async (req, res) => {
  try {
    const { namespace_id, name, rule, values } = req.body;
    const result = await policyClient.createAttribute(namespace_id, name, rule, values);
    res.status(201).json(result);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Key assignment endpoints
app.post('/api/attributes/namespace/key/assign', async (req, res) => {
  try {
    const { key_id, namespace_id } = req.body;
    const result = await policyClient.assignNamespaceKey(key_id, namespace_id);
    res.json(result);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/attributes/key/assign', async (req, res) => {
  try {
    const { key_id, attribute_id } = req.body;
    const result = await policyClient.assignAttributeKey(key_id, attribute_id);
    res.json(result);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/attributes/value/key/assign', async (req, res) => {
  try {
    const { key_id, value_id } = req.body;
    const result = await policyClient.assignValueKey(key_id, value_id);
    res.json(result);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/attributes/namespace/key/unassign', async (req, res) => {
  try {
    const { key_id, namespace_id } = req.body;
    const result = await policyClient.unassignNamespaceKey(key_id, namespace_id);
    res.json(result);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/attributes/key/unassign', async (req, res) => {
  try {
    const { key_id, attribute_id } = req.body;
    const result = await policyClient.unassignAttributeKey(key_id, attribute_id);
    res.json(result);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/attributes/value/key/unassign', async (req, res) => {
  try {
    const { key_id, value_id } = req.body;
    const result = await policyClient.unassignValueKey(key_id, value_id);
    res.json(result);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Subject Condition Set endpoints
app.post('/api/subject-condition-sets/create', async (req, res) => {
  try {
    const { subject_sets } = req.body;
    const result = await policyClient.createSubjectConditionSet(subject_sets);
    res.status(201).json(result);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/subject-mappings/create', async (req, res) => {
  try {
    const { attribute_value_id, subject_condition_set_id, action = 'read' } = req.body;
    const result = await policyClient.createSubjectMapping(attribute_value_id, subject_condition_set_id, action);
    res.status(201).json(result);
  } catch (error) {
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

function startServer() {
  server = app.listen(PORT, () => {
    console.log(`Test helper server running on port ${PORT}`);
    console.log(`Platform endpoint: ${PLATFORM_ENDPOINT}`);
  });
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