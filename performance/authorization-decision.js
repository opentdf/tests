import { getClient } from './keycloakData.js';
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter } from 'k6/metrics';
export const http_5xx_errors = new Counter('http_5xx_errors');

export default function() {
  // Get total VUs from environment variable or use a default value
  const totalVUs = __ENV.TOTAL_VUS ? parseInt(__ENV.TOTAL_VUS) : 1000;

  // Calculate padding digits based on total VUs
  const paddingDigits = totalVUs > 1 ? Math.floor(Math.log10(totalVUs - 1)) + 1 : 1;

  // Calculate client index (0-based) from VU number (1-based)
  const clientIndex = (__VU - 1) % totalVUs;

  // Format client ID with appropriate padding
  const paddedIndex = String(clientIndex).padStart(paddingDigits, '0');
  const clientId = `opentdf-${paddedIndex}`;

  // Get the client from keycloakData
  const client = getClient(clientId);

  if (__VU <= 10) {
    console.log(`VU ${__VU} using client ${clientId} ${client.clientId}`);
  }

  // Get URLs from environment variables or use defaults
  const keycloakBaseUrl = __ENV.KEYCLOAK_URL || 'http://localhost:8888';
  const authServiceBaseUrl = __ENV.API_URL || 'http://localhost:8080';
  const realmName = __ENV.REALM || 'opentdf';

  // Step 1: Get token endpoint from environment or discover it
  let tokenEndpoint;

  if (__ENV.AUTH_URL) {
    // Use the provided auth URL directly
    tokenEndpoint = __ENV.AUTH_URL;
    if (__VU === 1) {
      console.log(`Using AUTH_URL from environment: ${tokenEndpoint}`);
    }
  } else if (__VU === 1 || !__ENV.tokenEndpoint) {
    // Discover the token endpoint if not provided and not already discovered
    const realmInfoUrl = `${keycloakBaseUrl}/auth/realms/${realmName}`;

    const realmInfoResponse = http.get(realmInfoUrl);

    check(realmInfoResponse, {
      'Realm info retrieved': (r) => r.status === 200,
      'Token service URL available': (r) => r.json('token-service') !== undefined,
    });

    if (realmInfoResponse.status !== 200) {
      console.error(`Failed to get realm info: ${realmInfoResponse.status}`);
      return;
    }

    const realmInfo = JSON.parse(realmInfoResponse.body);
    tokenEndpoint = `${realmInfo['token-service']}/token`;
__ENV.tokenEndpoint = tokenEndpoint;

console.log(`Using discovered token endpoint: ${tokenEndpoint}`);
} else {
  // Use the previously discovered endpoint
  tokenEndpoint = __ENV.tokenEndpoint;
}

// Step 2: Get access token using client credentials
const tokenData = {
  'client_id': client.clientId,
  'client_secret': client.secret,
  'grant_type': 'client_credentials'
};

const tokenHeaders = {
  'Content-Type': 'application/x-www-form-urlencoded',
};

const tokenResponse = http.post(tokenEndpoint, tokenData, { headers: tokenHeaders });
if (tokenResponse.status >= 500 && tokenResponse.status < 600) http_5xx_errors.add(1);

// Make sure checks always run and have consistent names
const tokenCheck = check(tokenResponse, {
  'Token request successful': (r) => r.status === 200,
  'Access token received': (r) => r.json('access_token') !== undefined,
});

// Log failures to help debugging
if (!tokenCheck) {
  console.error(`Client credentials grant failed for ${client.clientId}: ${tokenResponse.status} ${tokenResponse.body}`);
  return;
}

const token = tokenResponse.json('access_token');

if (__VU <= 5) {
  console.log(`Successfully obtained access token for ${client.clientId}`);
}

// Step 3: Test the authorization service endpoints
const authHeaders = {
  'Authorization': `Bearer ${token}`,
  'Content-Type': 'application/json',
};

// Test /v1/authorization endpoint
const authorizationUrl = `${authServiceBaseUrl}/v1/authorization`;
const authorizationPayload = JSON.stringify({
  "decisionRequests": [
    {
      "actions": [
        {
          "name": "read"
        }
      ],
      "entityChains": [
        {
          "id": "ec1",
          "entities": [
            {
              "emailAddress": "bbb@topsecret.gbr"
            }
          ]
        }
      ],
      "resourceAttributes": [
        {
          "resourceAttributesId": "attr-set-1",
          "attributeValueFqns": [
            "https://demo.com/attr/classification/value/secret",
            "https://demo.com/attr/relto/value/usa",
            "https://demo.com/attr/relto/value/fvey"
          ]
        }
      ]
    }
  ]
});

const authorizationResponse = http.post(
  authorizationUrl,
  authorizationPayload,
  { headers: authHeaders }
);
if (authorizationResponse.status >= 500 && authorizationResponse.status < 600) http_5xx_errors.add(1);
check(authorizationResponse, {
  'Authorization endpoint returns 200': (r) => r.status === 200,
  'Authorization response has decisionResponses': (r) => r.json('decisionResponses') !== undefined,
});

if (__VU <= 5) {
  console.log(`Authorization response: ${authorizationResponse.status}`);

  // If there was an error, log it for debugging
  if (authorizationResponse.status !== 200) {
    console.log(`Authorization error: ${authorizationResponse.body}`);
  }
}

// Add small sleep to avoid overwhelming the service
sleep(0.1);
}

export function handleSummary(data) {
  // Get test duration in seconds
  const testDurationMs = data.state.testRunDurationMs;
  const testDuration = testDurationMs ? testDurationMs / 1000 : 0;

  // Get total HTTP requests
  const httpReqsMetric = data.metrics.http_reqs || {};
  const totalHttpRequests = httpReqsMetric.values ? (httpReqsMetric.values.count || 0) : 0;

  // Get total HTTP 5xx requests
  const http5xxErrorsCount = data.metrics.http_5xx_errors ? data.metrics.http_5xx_errors.values.count : 0;
  const http5xxErrorRate = totalHttpRequests > 0 ? (http5xxErrorsCount / totalHttpRequests) * 100 : 0;

  // For an HTTP test making 2 requests per iteration (token, authorization)
  // we can estimate the per-endpoint counts
  const iterations = data.metrics.iterations ? data.metrics.iterations.values.count : 0;

  // Estimate counts per endpoint (1 token request, 1 authorization per iteration)
  const tokenRequests = iterations;
  const authorizationRequests = iterations;

  // Calculate throughput based on estimated requests per endpoint
  const authorizationThroughput = testDuration > 0 ? authorizationRequests / testDuration : 0;

  // Response success estimate (if the iterations completed, we can assume most requests succeeded)
  // Based on total HTTP requests vs expected requests (2 per iteration)
  const expectedRequests = iterations * 2;
  const successRateEstimate = expectedRequests > 0 ? (Math.min(totalHttpRequests, expectedRequests) / expectedRequests) * 100 : 0;

  // Target throughput requirements
  const targetThroughput = 5000; // requests/sec
  const authorizationTargetMet = authorizationThroughput >= targetThroughput;

  // Get performance metrics
  const httpReqDurationMetrics = data.metrics.http_req_duration || {};
  const avgDuration = httpReqDurationMetrics.values ? (httpReqDurationMetrics.values.avg || 0) : 0;
  const p95Duration = httpReqDurationMetrics.values ? (httpReqDurationMetrics.values['p(95)'] || 0) : 0;

  // Get URLs for reporting
  const authUrl = __ENV.AUTH_URL || __ENV.tokenEndpoint || "default Keycloak URL";
  const apiUrl = __ENV.API_URL || "http://localhost:8080";

  return {
    'stdout': `
      OpenTDF Authorization Service Test Summary
      ------------------------------------------
      
      THROUGHPUT ANALYSIS:
      ✓ /v1/authorization: ${authorizationThroughput.toFixed(2)} req/sec [${authorizationTargetMet ? 'PASS' : 'FAIL'}] (Target: ${targetThroughput} req/sec)
      
      PERFORMANCE METRICS:
      - Average response time: ${avgDuration.toFixed(2)}ms
      - P95 response time: ${p95Duration.toFixed(2)}ms
      
      RELIABILITY METRICS:
      - Completed iterations: ${iterations}
      - Total HTTP requests: ${totalHttpRequests}
      - 5xx HTTP errors: ${http5xxErrorsCount} (${http5xxErrorRate.toFixed(2)}%)
      - Estimated success rate: ${(100 - http5xxErrorRate).toFixed(2)}%
      
      TEST CONFIGURATION:
      - Auth URL: ${authUrl}
      - API URL: ${apiUrl}
      - Virtual Users: ${__ENV.TOTAL_VUS || 0}
      - Test Duration: ${testDuration.toFixed(2)} seconds
      
      SUMMARY:
      The OpenTDF Authorization Service processed ${Math.round(authorizationThroughput)} requests/second under a 
      load of ${__ENV.TOTAL_VUS || 0} virtual users over ${testDuration.toFixed(0)} seconds, with an average 
      response time of ${avgDuration.toFixed(0)}ms and a P95 of ${p95Duration.toFixed(0)}ms.
      
      The system ${authorizationTargetMet ? 'MEETS' : 'DOES NOT MEET'} the target throughput 
      requirement of ${targetThroughput} requests/second.
    `,
  };
}
