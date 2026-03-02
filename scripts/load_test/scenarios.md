# K6 Load Test Scenarios

This document describes each load test scenario in detail, including their purpose, configuration, and expected behavior.

## Scenario Comparison

| Scenario | Duration | Max Users | Request Rate | Purpose |
|----------|----------|-----------|--------------|---------|
| chat_load | 15m | 40 | ~40 req/s | Validate chat completion endpoint |
| rag_load | 15m | 30 | ~30 req/s | Validate RAG ingest & query |
| mcp_load | 15m | 20 | ~20 req/s | Validate MCP tool execution |
| adaptive_load_scenario | 18m | 100 | ~100 req/s | Validate system under adaptive load |
| workspace_quota_burst_scenario | 3m | 200 | 100 req/s | Validate rate limiting & quota enforcement |

## 1. chat_load

**Purpose**: Validate the chat completion endpoint under realistic load patterns.

**Configuration**:
```javascript
executor: 'ramping-vus'
startVUs: 0
stages: [
    { duration: '2m', target: 20 },   // Ramp up
    { duration: '5m', target: 20 },   // Sustain
    { duration: '2m', target: 40 },   // Increase
    { duration: '5m', target: 40 },   // Sustain peak
    { duration: '1m', target: 0 },    // Ramp down
]
```

**Request Pattern**:
- Random chat messages from predefined set
- Model: `llama-3.3-8b-instruct`
- Max tokens: 150
- Temperature: 0.7
- Sleep: 1-3 seconds between requests

**Thresholds**:
- P95 latency: < 1500ms
- P99 latency: < 2000ms
- Error rate: < 1%

**Expected Behavior**:
- Steady response times at 20 users
- Slight latency increase at 40 users
- All responses should contain valid chat completions

## 2. rag_load

**Purpose**: Validate RAG operations (document ingestion and querying) under load.

**Configuration**:
```javascript
executor: 'ramping-vus'
startVUs: 0
stages: [
    { duration: '2m', target: 15 },
    { duration: '5m', target: 15 },
    { duration: '2m', target: 30 },
    { duration: '5m', target: 30 },
    { duration: '1m', target: 0 },
]
```

**Request Pattern**:
- 30% document ingest operations
- 70% query operations
- Random queries from predefined set
- Top-k: 5 documents per query
- Sleep: 2-4 seconds between requests

**Thresholds**:
- P95 latency: < 1800ms
- P99 latency: < 2000ms
- Error rate: < 1%

**Expected Behavior**:
- Ingest operations may be slightly slower than queries
- Query results should always return relevant documents
- Vector similarity search should be performant

## 3. mcp_load

**Purpose**: Validate MCP (Model Context Protocol) tool execution under load.

**Configuration**:
```javascript
executor: 'ramping-vus'
startVUs: 0
stages: [
    { duration: '2m', target: 10 },
    { duration: '5m', target: 10 },
    { duration: '2m', target: 20 },
    { duration: '5m', target: 20 },
    { duration: '1m', target: 0 },
]
```

**Request Pattern**:
- Random MCP tool requests (filesystem, github, notion)
- Various operations per tool
- Sleep: 2-5 seconds between requests

**Thresholds**:
- P95 latency: < 1500ms
- P99 latency: < 2000ms
- Error rate: < 1%

**Expected Behavior**:
- Async operations may return 202 status
- Tool execution should be reliable
- External service calls may have variable latency

## 4. adaptive_load_scenario

**Purpose**: Validate system behavior under adaptive, increasing load across all endpoints.

**Configuration**:
```javascript
executor: 'ramping-vus'
startVUs: 0
stages: [
    { duration: '1m', target: 10 },    // Warm up
    { duration: '2m', target: 25 },    // Gradual increase
    { duration: '2m', target: 50 },    // Mid-range load
    { duration: '2m', target: 75 },    // Higher load
    { duration: '3m', target: 100 },   // Ramp to peak
    { duration: '5m', target: 100 },   // Sustain peak load
    { duration: '2m', target: 50 },    // Gradual ramp down
    { duration: '1m', target: 0 },     // Cool down
]
```

**Request Pattern**:
- Random endpoint selection (chat, RAG, MCP)
- Distributed across 10 workspaces
- Each request includes workspace ID header
- Sleep: 1-2 seconds between requests

**Thresholds**:
- P95 latency: < 1800ms
- P99 latency: < 2000ms
- Error rate: < 0.5% (strict SLO)

**Expected Behavior**:
- System should scale smoothly from 10 to 100 users
- No degradation at 100 concurrent users
- All endpoints should maintain SLOs
- Workspace isolation should be maintained

**Key Metrics**:
- `adaptive_latency_ms`: Latency trend across all endpoints
- `adaptive_errors`: Combined error rate

**Use Cases**:
- Production capacity planning
- SLO validation under realistic traffic
- Multi-tenant performance testing
- System scalability assessment

## 5. workspace_quota_burst_scenario

**Purpose**: Validate workspace quota enforcement and rate limiting under burst traffic.

**Configuration**:
```javascript
executor: 'constant-arrival-rate'
duration: '3m'
rate: 100  // 100 requests per second (10x normal)
timeUnit: '1s'
preAllocatedVUs: 50
maxVUs: 200
startTime: '18m'  // Starts after adaptive_load_scenario
```

**Request Pattern**:
- All requests to chat completion endpoint
- Distributed across 5 "burst" workspaces
- Smaller token limit (50 tokens) for faster responses
- No sleep between requests (constant rate)

**Thresholds**:
- P95 latency: < 2000ms
- P99 latency: < 3000ms (relaxed for burst)
- Rate limited: > 50% (expects rate limiting)

**Expected Behavior**:
- **Initial burst**: First requests succeed (200 OK)
- **Rate limiting kicks in**: 429 Too Many Requests
- **Quota exhaustion**: 402 Payment Required or 403 Forbidden
- **System stability**: No crashes or timeouts
- **Graceful degradation**: Clear error messages

**Key Metrics**:
- `quota_burst_rate_limited`: Percentage of requests that hit limits
- `rate_limited_requests`: Count of 429 responses
- `quota_exceeded_requests`: Count of quota exhaustion (402/403)
- `quota_burst_latency_ms`: Latency even under rate limiting

**HTTP Status Codes**:
- `200 OK`: Request succeeded (within quota)
- `429 Too Many Requests`: Rate limit exceeded
- `402 Payment Required`: Quota exhausted (billing required)
- `403 Forbidden`: Quota exceeded (access denied)

**Use Cases**:
- Validate rate limiting implementation
- Test quota enforcement accuracy
- Verify billing/metering system
- Ensure system stability under abuse scenarios
- Validate error messaging for quota violations

**Success Criteria**:
- At least 50% of requests should be rate limited
- System should remain stable (no 500 errors)
- Rate limiting should engage quickly (within seconds)
- Clear error messages in responses
- No impact on other workspaces

## Running Individual Scenarios

To run a single scenario (requires modifications to k6_load_test.js):

```bash
# Temporarily disable other scenarios by commenting them out
# Then run:
k6 run k6_load_test.js
```

Or use k6 tags to filter scenarios (if implemented):

```bash
k6 run --tag scenario=adaptive k6_load_test.js
```

## Scenario Timing

All scenarios run with the following timeline:

```
Time | Scenarios Running
-----|------------------
0:00 | chat_load, rag_load, mcp_load start
15:00| chat_load, rag_load, mcp_load complete
0:00 | adaptive_load_scenario starts
18:00| adaptive_load_scenario completes
18:00| workspace_quota_burst_scenario starts
21:00| workspace_quota_burst_scenario completes
```

**Total test duration**: ~21 minutes

## Interpreting Results

### Successful Test Run
```
SLO Validation:
  ✓ Error rate SLO passed: 0.123% ≤ 0.5%
  ✓ P99 latency SLO passed: 1856ms ≤ 2000ms
  ✓ Availability SLO passed: 99.88% ≥ 99.5%
```

### Failed Test Run (SLO Violation)
```
SLO Validation:
  ✗ Error rate SLO violated: 0.789% > 0.5%
  ✓ P99 latency SLO passed: 1923ms ≤ 2000ms
  ✗ Availability SLO violated: 99.21% < 99.5%
```

### Quota Burst Success
```
Quota Burst Rate Limited: 67.45%
Rate Limited Requests: 12150
Quota Exceeded Requests: 3421
```

## Scenario Evolution

As the system evolves, scenarios can be extended:

1. **Add new endpoints**: Include new API endpoints in adaptive scenario
2. **Increase load**: Ramp up to higher concurrent users (150, 200)
3. **Longer duration**: Extend sustain periods for soak testing
4. **Custom patterns**: Create scenarios for specific use cases
5. **Chaos testing**: Combine with chaos engineering (pod failures, network latency)

## Related Documentation

- [README.md](./README.md): Full load test suite documentation
- [k6_load_test.js](../../k6_load_test.js): Load test script implementation
- [run_k6_suite.sh](./run_k6_suite.sh): Test execution script
