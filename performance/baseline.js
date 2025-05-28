import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter } from 'k6/metrics';

export const http_5xx_errors = new Counter('http_5xx_errors');

export default function() {
  // Get API URL from environment or use default
  const apiUrl = __ENV.API_URL || 'http://localhost:8080';

  // Test the well-known configuration endpoint (gRPC endpoint)
  const wellKnownUrl = `${apiUrl}/wellknownconfiguration.WellKnownService/GetWellKnownConfiguration`;

  // gRPC endpoints typically expect POST with proper content type
  const headers = {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
  };

  // Empty JSON payload for the gRPC call
  const payload = JSON.stringify({});

  const response = http.post(wellKnownUrl, payload, { headers: headers });

  // Track 5xx errors
  if (response.status >= 500 && response.status < 600) {
    http_5xx_errors.add(1);
  }

  // Check response
  check(response, {
    'Well-known endpoint returns 200': (r) => r.status === 200,
    'Response has body': (r) => r.body && r.body.length > 0,
  });

  if (__VU <= 5) {
    console.log(`Well-known response: ${response.status}`);
  }

  // Small sleep to avoid overwhelming the service
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

  // Get iterations (1 request per iteration for this test)
  const iterations = data.metrics.iterations ? data.metrics.iterations.values.count : 0;

  // Calculate throughput
  const throughput = testDuration > 0 ? totalHttpRequests / testDuration : 0;

  // Target throughput requirements
  const targetThroughput = 5000; // requests/sec
  const targetMet = throughput >= targetThroughput;

  // Get performance metrics
  const httpReqDurationMetrics = data.metrics.http_req_duration || {};
  const avgDuration = httpReqDurationMetrics.values ? (httpReqDurationMetrics.values.avg || 0) : 0;
  const p95Duration = httpReqDurationMetrics.values ? (httpReqDurationMetrics.values['p(95)'] || 0) : 0;

  // Get API URL for reporting
  const apiUrl = __ENV.API_URL || "http://localhost:8080";

  return {
    'stdout': `
      Well-Known Configuration Endpoint Baseline Test
      -----------------------------------------------
      
      THROUGHPUT ANALYSIS:
      ✓ /wellknownconfiguration: ${throughput.toFixed(2)} req/sec [${targetMet ? 'PASS' : 'FAIL'}] (Target: ${targetThroughput} req/sec)
      
      PERFORMANCE METRICS:
      - Average response time: ${avgDuration.toFixed(2)}ms
      - P95 response time: ${p95Duration.toFixed(2)}ms
      
      RELIABILITY METRICS:
      - Completed iterations: ${iterations}
      - Total HTTP requests: ${totalHttpRequests}
      - 5xx HTTP errors: ${http5xxErrorsCount} (${http5xxErrorRate.toFixed(2)}%)
      - Success rate: ${(100 - http5xxErrorRate).toFixed(2)}%
      
      TEST CONFIGURATION:
      - API URL: ${apiUrl}
      - Virtual Users: ${__ENV.TOTAL_VUS || 'default'}
      - Test Duration: ${testDuration.toFixed(2)} seconds
      
      BASELINE SUMMARY:
      The well-known configuration endpoint processed ${Math.round(throughput)} requests/second 
      under a load of ${__ENV.TOTAL_VUS || 'default'} virtual users over ${testDuration.toFixed(0)} seconds, 
      with an average response time of ${avgDuration.toFixed(0)}ms and a P95 of ${p95Duration.toFixed(0)}ms.
      
      This baseline ${targetMet ? 'MEETS' : 'DOES NOT MEET'} the target throughput requirement 
      of ${targetThroughput} requests/second.
    `,
  };
}
