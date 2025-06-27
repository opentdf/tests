import { getClient } from './keycloakData.js';
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter } from 'k6/metrics';
export const http_5xx_errors = new Counter('http_5xx_errors');
export const skipped_iterations = new Counter('skipped_iterations');
export const token_requests = new Counter('token_requests');
export const token_failures = new Counter('token_failures');

// Token refresh interval in seconds (3 minutes)
const TOKEN_REFRESH_INTERVAL = 180;

// Per-VU token storage using k6 scenario state
const vuTokens = {};

export default function() {
  // Format client ID with appropriate padding
  const clientId = `opentdf`;

  // Get the client from keycloakData
  const client = getClient(clientId);

  if (__ITER === 0) {
    console.log(`VU ${__VU} using client ${clientId} ${client.clientId}`);
  }

  // Get URLs from environment variables or use defaults
  const keycloakBaseUrl = __ENV.KEYCLOAK_URL || 'http://localhost:8888';
  const serviceBaseUrl = __ENV.API_URL || 'http://localhost:8080';
  const realmName = __ENV.REALM || 'opentdf';

  // Get the current time to check if we need a new token
  const currentTime = Math.floor(Date.now() / 1000); // Current time in seconds
  
  // Each VU has its own token
  const vuKey = `vu-${__VU}`;
  let token = null;
  
  // Check if this VU has a valid token
  if (vuTokens[vuKey] && 
      vuTokens[vuKey].token && 
      (currentTime - vuTokens[vuKey].timestamp) < TOKEN_REFRESH_INTERVAL) {
    // Use the existing token
    token = vuTokens[vuKey].token;
  } else {
    // Get a new token for this VU
    let tokenEndpoint;
    
    // Get token endpoint directly from ENV or use default
    if (__ENV.AUTH_URL) {
      tokenEndpoint = __ENV.AUTH_URL;
    } else {
      tokenEndpoint = `${keycloakBaseUrl}/auth/realms/${realmName}/protocol/openid-connect/token`;
    }
    
    // Prepare token request data
    const tokenData = {
      'client_id': client.clientId,
      'client_secret': client.secret,
      'grant_type': 'client_credentials'
    };

    const tokenHeaders = {
      'Content-Type': 'application/x-www-form-urlencoded',
    };

    // Count token requests
    token_requests.add(1);
    
    // Make the token request
    const tokenResponse = http.post(tokenEndpoint, tokenData, { headers: tokenHeaders });
    
    if (__ITER === 0 || __ITER % 100 === 0) {
      console.log(`VU ${__VU} - Token request status: ${tokenResponse.status}`);
    }
    
    if (tokenResponse.status >= 500 && tokenResponse.status < 600) {
      http_5xx_errors.add(1);
    }
    
    if (tokenResponse.status === 200) {
      try {
        const responseBody = JSON.parse(tokenResponse.body);
        if (responseBody.access_token) {
          // Save the token for this VU
          vuTokens[vuKey] = {
            token: responseBody.access_token,
            timestamp: currentTime
          };
          
          token = responseBody.access_token;
          
          if (__ITER === 0) {
            console.log(`VU ${__VU} - Successfully obtained token`);
          }
        } else {
          token_failures.add(1);
          console.error(`VU ${__VU} - No access_token in response`);
        }
      } catch (e) {
        token_failures.add(1);
        console.error(`VU ${__VU} - Error parsing token response: ${e.message}`);
      }
    } else {
      token_failures.add(1);
      console.error(`VU ${__VU} - Token request failed with status ${tokenResponse.status}`);
    }
  }
  
  // If no token is available, skip this iteration
  if (!token) {
    console.log(`VU ${__VU} - Failed to get token, skipping this iteration`);
    skipped_iterations.add(1);
    return;
  }

  // Step 3: Test the SharePoint webhook endpoint
  const sharePointHeaders = {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/xml',
  };

  // Create a random UUID for the correlation ID
  const generateUUID = () => {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
      const r = Math.random() * 16 | 0,
        v = c === 'x' ? r : (r & 0x3 | 0x8);
      return v.toString(16);
    });
  };
  
  const correlationId = generateUUID();
  const listId = generateUUID();
  const listItemId = Math.floor(Math.random() * 1000) + 1;
  const userId = Math.floor(Math.random() * 100) + 1;
  const userEmail = `user${userId}@contoso.com`;

  // SharePoint webhook XML payload
  const sharePointPayload = `<?xml version="1.0" encoding="UTF-8"?>
<Envelope xmlns="http://schemas.xmlsoap.org/soap/envelope/">
  <Body>
    <ProcessEvent xmlns="http://schemas.microsoft.com/sharepoint/remoteapp/">
      <properties>
        <AppEventProperties></AppEventProperties>
        <ContextToken>sample-context-token-value</ContextToken>
        <CorrelationId>${correlationId}</CorrelationId>
        <ErrorCode></ErrorCode>
        <ErrorMessage></ErrorMessage>
        <EventType>ItemAdded</EventType>
        <ItemEventProperties>
          <BeforeProperties>
            <KeyValueOfstringanyType xmlns="http://schemas.microsoft.com/2003/10/Serialization/Arrays">
              <Key>Title</Key>
              <Value xmlns:i="http://www.w3.org/2001/XMLSchema-instance" i:type="string"></Value>
            </KeyValueOfstringanyType>
          </BeforeProperties>
          <AfterProperties>
            <KeyValueOfstringanyType xmlns="http://schemas.microsoft.com/2003/10/Serialization/Arrays">
              <Key>Title</Key>
              <Value xmlns:i="http://www.w3.org/2001/XMLSchema-instance" i:type="string">New Document</Value>
            </KeyValueOfstringanyType>
            <KeyValueOfstringanyType xmlns="http://schemas.microsoft.com/2003/10/Serialization/Arrays">
              <Key>FileLeafRef</Key>
              <Value xmlns:i="http://www.w3.org/2001/XMLSchema-instance" i:type="string">document-${__VU}-${Date.now()}.docx</Value>
            </KeyValueOfstringanyType>
          </AfterProperties>
          <AfterUrl>https://contoso.sharepoint.com/sites/site/Shared%20Documents/document-${__VU}.docx</AfterUrl>
          <BeforeUrl></BeforeUrl>
          <ListId>${listId}</ListId>
          <ListTitle>Documents</ListTitle>
          <ListItemId>${listItemId}</ListItemId>
          <WebUrl>https://contoso.sharepoint.com/sites/site</WebUrl>
          <CurrentUserId>${userId}</CurrentUserId>
          <UserLoginName>${userEmail}</UserLoginName>
        </ItemEventProperties>
      </properties>
    </ProcessEvent>
  </Body>
</Envelope>`;

  // SharePoint webhook endpoint URL
  const sharePointUrl = `${serviceBaseUrl}/sharepoint/listen/itemadded`;

  const sharePointResponse = http.post(
    sharePointUrl,
    sharePointPayload,
    { headers: sharePointHeaders }
  );
  if (sharePointResponse.status >= 500 && sharePointResponse.status < 600) http_5xx_errors.add(1);
  
  check(sharePointResponse, {
    'SharePoint webhook returns 200': (r) => r.status === 200
  });

  // Log errors
  if (sharePointResponse.status !== 200 && (__ITER === 0 || __ITER % 100 === 0)) {
    console.log(`VU ${__VU} - SharePoint webhook error: ${sharePointResponse.status} - ${sharePointResponse.body}`);
  }

  // Add small sleep to avoid overwhelming the service
  sleep(1);
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
  
  // Get metrics related to token handling
  const skippedIterationsCount = data.metrics.skipped_iterations ? data.metrics.skipped_iterations.values.count : 0;
  const tokenRequestsCount = data.metrics.token_requests ? data.metrics.token_requests.values.count : 0;
  const tokenFailuresCount = data.metrics.token_failures ? data.metrics.token_failures.values.count : 0;
  const tokenSuccessRate = tokenRequestsCount > 0 ? ((tokenRequestsCount - tokenFailuresCount) / tokenRequestsCount) * 100 : 0;

  // For an HTTP test making 2 requests per iteration (token, sharepoint webhook)
  // we can estimate the per-endpoint counts
  const iterations = data.metrics.iterations ? data.metrics.iterations.values.count : 0;

  // Estimate counts per endpoint (1 token request, 1 SharePoint webhook request per iteration)
  const tokenRequests = iterations;
  const sharePointRequests = iterations;

  // Calculate throughput based on estimated requests per endpoint
  const sharePointThroughput = testDuration > 0 ? sharePointRequests / testDuration : 0;

  // Response success estimate (if the iterations completed, we can assume most requests succeeded)
  // Based on total HTTP requests vs expected requests (2 per iteration)
  const expectedRequests = iterations * 2;
  const successRateEstimate = expectedRequests > 0 ? (Math.min(totalHttpRequests, expectedRequests) / expectedRequests) * 100 : 0;

  // Target throughput requirements
  const targetThroughput = 5000; // requests/sec
  const sharePointTargetMet = sharePointThroughput >= targetThroughput;

  // Get performance metrics
  const httpReqDurationMetrics = data.metrics.http_req_duration || {};
  const avgDuration = httpReqDurationMetrics.values ? (httpReqDurationMetrics.values.avg || 0) : 0;
  const p95Duration = httpReqDurationMetrics.values ? (httpReqDurationMetrics.values['p(95)'] || 0) : 0;

  // Get URLs for reporting
  const authUrl = __ENV.AUTH_URL || __ENV.tokenEndpoint || "default Keycloak URL";
  const apiUrl = __ENV.API_URL || "http://localhost:8080";
  
  // Calculate estimated token refreshes based on test duration
  const estimatedTokenRefreshes = Math.max(1, Math.floor(testDuration / TOKEN_REFRESH_INTERVAL));

  return {
    'stdout': `
      SharePoint Webhook Performance Test Summary
      ------------------------------------------
      
      THROUGHPUT ANALYSIS:
      ✓ /sharepoint/listen/itemadded: ${sharePointThroughput.toFixed(2)} req/sec [${sharePointTargetMet ? 'PASS' : 'FAIL'}] (Target: ${targetThroughput} req/sec)
      
      PERFORMANCE METRICS:
      - Average response time: ${avgDuration.toFixed(2)}ms
      - P95 response time: ${p95Duration.toFixed(2)}ms
      
      RELIABILITY METRICS:
      - Completed iterations: ${iterations}
      - Skipped iterations (no token): ${skippedIterationsCount}
      - Total HTTP requests: ${totalHttpRequests}
      - Token requests: ${tokenRequestsCount}
      - Token failures: ${tokenFailuresCount} (${tokenSuccessRate.toFixed(2)}% success)
      - 5xx HTTP errors: ${http5xxErrorsCount} (${http5xxErrorRate.toFixed(2)}%)
      - Estimated success rate: ${(100 - http5xxErrorRate).toFixed(2)}%
      
      TEST CONFIGURATION:
      - Auth URL: ${authUrl}
      - API URL: ${apiUrl}
      - Virtual Users: ${__ENV.TOTAL_VUS || 0}
      - Test Duration: ${testDuration.toFixed(2)} seconds
      - Token Refresh Interval: ${TOKEN_REFRESH_INTERVAL} seconds
      - Estimated Token Refreshes: ${estimatedTokenRefreshes}
      
      SUMMARY:
      The SharePoint webhook service processed ${Math.round(sharePointThroughput)} requests/second under a 
      load of ${__ENV.TOTAL_VUS || 0} virtual users over ${testDuration.toFixed(0)} seconds, with an average 
      response time of ${avgDuration.toFixed(0)}ms and a P95 of ${p95Duration.toFixed(0)}ms.
      
      The system ${sharePointTargetMet ? 'MEETS' : 'DOES NOT MEET'} the target throughput 
      requirement of ${targetThroughput} requests/second.
    `,
  };
}
