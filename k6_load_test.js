// K6 Load Testing Script for Production Validation
// Tests: Chat, RAG, MCP endpoints with 50 concurrent users
// Run: k6 run --vus 50 --duration 10m k6_load_test.js

import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';
import { randomIntBetween, randomItem } from 'https://jslib.k6.io/k6-utils/1.2.0/index.js';

// Custom metrics
const chatErrors = new Rate('chat_errors');
const ragErrors = new Rate('rag_errors');
const mcpErrors = new Rate('mcp_errors');
const adaptiveErrors = new Rate('adaptive_errors');
const quotaBurstRateLimited = new Rate('quota_burst_rate_limited');
const chatLatency = new Trend('chat_latency_ms');
const ragLatency = new Trend('rag_latency_ms');
const mcpLatency = new Trend('mcp_latency_ms');
const adaptiveLatency = new Trend('adaptive_latency_ms');
const quotaBurstLatency = new Trend('quota_burst_latency_ms');
const totalRequests = new Counter('total_requests');
const rateLimitedRequests = new Counter('rate_limited_requests');
const quotaExceededRequests = new Counter('quota_exceeded_requests');

// Configuration
const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const GATEWAY_URL = __ENV.GATEWAY_URL || 'http://localhost:9002';
const MCP_URL = __ENV.MCP_URL || 'http://localhost:9100';

// Test options - SLO: P99 latency < 2s
export const options = {
    scenarios: {
        chat_load: {
            executor: 'ramping-vus',
            exec: 'chatScenario',
            startVUs: 0,
            stages: [
                { duration: '2m', target: 20 },  // Ramp up to 20 users
                { duration: '5m', target: 20 },  // Stay at 20 users
                { duration: '2m', target: 40 },  // Ramp up to 40 users
                { duration: '5m', target: 40 },  // Stay at 40 users
                { duration: '1m', target: 0 },   // Ramp down
            ],
            gracefulRampDown: '30s',
        },
        rag_load: {
            executor: 'ramping-vus',
            exec: 'ragScenario',
            startVUs: 0,
            stages: [
                { duration: '2m', target: 15 },
                { duration: '5m', target: 15 },
                { duration: '2m', target: 30 },
                { duration: '5m', target: 30 },
                { duration: '1m', target: 0 },
            ],
            gracefulRampDown: '30s',
        },
        mcp_load: {
            executor: 'ramping-vus',
            exec: 'mcpScenario',
            startVUs: 0,
            stages: [
                { duration: '2m', target: 10 },
                { duration: '5m', target: 10 },
                { duration: '2m', target: 20 },
                { duration: '5m', target: 20 },
                { duration: '1m', target: 0 },
            ],
            gracefulRampDown: '30s',
        },
        adaptive_load_scenario: {
            executor: 'ramping-vus',
            exec: 'adaptiveLoadScenario',
            startVUs: 0,
            stages: [
                { duration: '1m', target: 10 },   // Warm up
                { duration: '2m', target: 25 },   // Gradual increase
                { duration: '2m', target: 50 },   // Mid-range load
                { duration: '2m', target: 75 },   // Higher load
                { duration: '3m', target: 100 },  // Peak load - 100 concurrent users
                { duration: '5m', target: 100 },  // Sustain peak load
                { duration: '2m', target: 50 },   // Gradual ramp down
                { duration: '1m', target: 0 },    // Cool down
            ],
            gracefulRampDown: '30s',
        },
        workspace_quota_burst_scenario: {
            executor: 'constant-arrival-rate',
            exec: 'workspaceQuotaBurstScenario',
            duration: '3m',
            rate: 100,  // 100 requests per timeUnit (10x normal rate of ~10 req/s)
            timeUnit: '1s',
            preAllocatedVUs: 50,
            maxVUs: 200,
            startTime: '18m',  // Start after adaptive_load_scenario completes
        },
    },
    thresholds: {
        'http_req_duration': ['p(99)<2000'],  // SLO: P99 < 2s
        'http_req_duration{scenario:chat}': ['p(95)<1500', 'p(99)<2000'],
        'http_req_duration{scenario:rag}': ['p(95)<1800', 'p(99)<2000'],
        'http_req_duration{scenario:mcp}': ['p(95)<1500', 'p(99)<2000'],
        'http_req_duration{scenario:adaptive}': ['p(95)<1800', 'p(99)<2000'],
        'http_req_duration{scenario:quota_burst}': ['p(95)<2000', 'p(99)<3000'],
        'http_req_failed': ['rate<0.005'],  // SLO: 99.5% availability (error rate < 0.5%)
        'chat_errors': ['rate<0.01'],
        'rag_errors': ['rate<0.01'],
        'mcp_errors': ['rate<0.01'],
        'adaptive_errors': ['rate<0.005'],  // Strict SLO for adaptive scenario
        'quota_burst_rate_limited': ['rate>0.5'],  // Expect >50% rate limiting during burst
    },
};

// Test data
const chatMessages = [
    [{ role: 'user', content: 'What is machine learning?' }],
    [{ role: 'user', content: 'Explain neural networks in simple terms.' }],
    [{ role: 'user', content: 'How do I implement a REST API in Python?' }],
    [{ role: 'user', content: 'What are the best practices for code review?' }],
    [{ role: 'user', content: 'Describe the SOLID principles.' }],
];

const ragQueries = [
    'How do I deploy this application?',
    'What are the configuration options?',
    'Explain the architecture of the system',
    'What dependencies does this project have?',
    'How do I run the tests?',
];

const mcpRequests = [
    { tool: 'filesystem', operation: 'list_directory', path: '/workspace' },
    { tool: 'github', operation: 'get_repo_info', repo: 'test/repo' },
    { tool: 'notion', operation: 'search_pages', query: 'documentation' },
];

// Chat scenario
export function chatScenario() {
    group('Chat Completions', () => {
        const messages = randomItem(chatMessages);
        const payload = JSON.stringify({
            model: 'llama-3.3-8b-instruct',
            messages: messages,
            max_tokens: 150,
            temperature: 0.7,
        });

        const params = {
            headers: {
                'Content-Type': 'application/json',
            },
            tags: { scenario: 'chat' },
        };

        const startTime = Date.now();
        const response = http.post(`${BASE_URL}/v1/chat/completions`, payload, params);
        const duration = Date.now() - startTime;

        totalRequests.add(1);
        chatLatency.add(duration);

        const success = check(response, {
            'chat status 200': (r) => r.status === 200,
            'chat has content': (r) => {
                try {
                    const body = JSON.parse(r.body);
                    return body.choices && body.choices.length > 0;
                } catch (e) {
                    return false;
                }
            },
            'chat response time < 2s': (r) => duration < 2000,
        });

        chatErrors.add(!success);
    });

    sleep(randomIntBetween(1, 3));
}

// RAG scenario
export function ragScenario() {
    group('RAG Operations', () => {
        // Ingest document
        if (Math.random() < 0.3) {
            const ingestPayload = JSON.stringify({
                documents: [
                    {
                        content: `Test document ${Date.now()}`,
                        metadata: {
                            source: 'load_test',
                            timestamp: new Date().toISOString(),
                        },
                    },
                ],
            });

            const ingestParams = {
                headers: { 'Content-Type': 'application/json' },
                tags: { scenario: 'rag', operation: 'ingest' },
            };

            const startTime = Date.now();
            const response = http.post(`${GATEWAY_URL}/rag/ingest`, ingestPayload, ingestParams);
            const duration = Date.now() - startTime;

            totalRequests.add(1);
            ragLatency.add(duration);

            const success = check(response, {
                'rag ingest status 200': (r) => r.status === 200,
                'rag ingest response time < 2s': (r) => duration < 2000,
            });

            ragErrors.add(!success);
        }

        // Query documents
        const query = randomItem(ragQueries);
        const queryPayload = JSON.stringify({
            query: query,
            top_k: 5,
        });

        const queryParams = {
            headers: { 'Content-Type': 'application/json' },
            tags: { scenario: 'rag', operation: 'query' },
        };

        const startTime = Date.now();
        const response = http.post(`${GATEWAY_URL}/rag/query`, queryPayload, queryParams);
        const duration = Date.now() - startTime;

        totalRequests.add(1);
        ragLatency.add(duration);

        const success = check(response, {
            'rag query status 200': (r) => r.status === 200,
            'rag has results': (r) => {
                try {
                    const body = JSON.parse(r.body);
                    return body.results !== undefined;
                } catch (e) {
                    return false;
                }
            },
            'rag query response time < 2s': (r) => duration < 2000,
        });

        ragErrors.add(!success);
    });

    sleep(randomIntBetween(2, 4));
}

// MCP scenario
export function mcpScenario() {
    group('MCP Operations', () => {
        const request = randomItem(mcpRequests);
        const payload = JSON.stringify(request);

        const params = {
            headers: { 'Content-Type': 'application/json' },
            tags: { scenario: 'mcp' },
        };

        const startTime = Date.now();
        const response = http.post(`${MCP_URL}/mcp/execute`, payload, params);
        const duration = Date.now() - startTime;

        totalRequests.add(1);
        mcpLatency.add(duration);

        const success = check(response, {
            'mcp status 200 or 202': (r) => r.status === 200 || r.status === 202,
            'mcp response time < 2s': (r) => duration < 2000,
        });

        mcpErrors.add(!success);
    });

    sleep(randomIntBetween(2, 5));
}

// Adaptive load scenario - tests all endpoints with ramping load up to 100 users
export function adaptiveLoadScenario() {
    const endpoints = ['chat', 'rag', 'mcp'];
    const endpoint = randomItem(endpoints);
    
    group('Adaptive Load - Mixed Endpoints', () => {
        let response, duration, success;
        const startTime = Date.now();
        
        if (endpoint === 'chat') {
            const messages = randomItem(chatMessages);
            const payload = JSON.stringify({
                model: 'llama-3.3-8b-instruct',
                messages: messages,
                max_tokens: 150,
                temperature: 0.7,
            });
            
            const params = {
                headers: {
                    'Content-Type': 'application/json',
                    'X-Workspace-ID': `workspace-${(__VU % 10) + 1}`,
                },
                tags: { scenario: 'adaptive', endpoint: 'chat' },
            };
            
            response = http.post(`${BASE_URL}/v1/chat/completions`, payload, params);
            duration = Date.now() - startTime;
            
            success = check(response, {
                'adaptive chat status 200': (r) => r.status === 200,
                'adaptive chat has content': (r) => {
                    try {
                        const body = JSON.parse(r.body);
                        return body.choices && body.choices.length > 0;
                    } catch (e) {
                        return false;
                    }
                },
                'adaptive chat response time < 2s': (r) => duration < 2000,
            });
            
        } else if (endpoint === 'rag') {
            const query = randomItem(ragQueries);
            const payload = JSON.stringify({
                query: query,
                top_k: 5,
                workspace_id: `workspace-${(__VU % 10) + 1}`,
            });
            
            const params = {
                headers: {
                    'Content-Type': 'application/json',
                    'X-Workspace-ID': `workspace-${(__VU % 10) + 1}`,
                },
                tags: { scenario: 'adaptive', endpoint: 'rag' },
            };
            
            response = http.post(`${GATEWAY_URL}/rag/query`, payload, params);
            duration = Date.now() - startTime;
            
            success = check(response, {
                'adaptive rag status 200': (r) => r.status === 200,
                'adaptive rag has results': (r) => {
                    try {
                        const body = JSON.parse(r.body);
                        return body.results !== undefined;
                    } catch (e) {
                        return false;
                    }
                },
                'adaptive rag response time < 2s': (r) => duration < 2000,
            });
            
        } else {
            const request = randomItem(mcpRequests);
            const payload = JSON.stringify({
                ...request,
                workspace_id: `workspace-${(__VU % 10) + 1}`,
            });
            
            const params = {
                headers: {
                    'Content-Type': 'application/json',
                    'X-Workspace-ID': `workspace-${(__VU % 10) + 1}`,
                },
                tags: { scenario: 'adaptive', endpoint: 'mcp' },
            };
            
            response = http.post(`${MCP_URL}/mcp/execute`, payload, params);
            duration = Date.now() - startTime;
            
            success = check(response, {
                'adaptive mcp status 200 or 202': (r) => r.status === 200 || r.status === 202,
                'adaptive mcp response time < 2s': (r) => duration < 2000,
            });
        }
        
        totalRequests.add(1);
        adaptiveLatency.add(duration);
        adaptiveErrors.add(!success);
    });
    
    sleep(randomIntBetween(1, 2));
}

// Workspace quota burst scenario - sends 10x normal rate to test metering and rate limiting
export function workspaceQuotaBurstScenario() {
    const workspaceId = `burst-workspace-${(__VU % 5) + 1}`;
    
    group('Quota Burst Test', () => {
        const messages = randomItem(chatMessages);
        const payload = JSON.stringify({
            model: 'llama-3.3-8b-instruct',
            messages: messages,
            max_tokens: 50,
            temperature: 0.7,
        });
        
        const params = {
            headers: {
                'Content-Type': 'application/json',
                'X-Workspace-ID': workspaceId,
            },
            tags: { scenario: 'quota_burst' },
        };
        
        const startTime = Date.now();
        const response = http.post(`${BASE_URL}/v1/chat/completions`, payload, params);
        const duration = Date.now() - startTime;
        
        totalRequests.add(1);
        quotaBurstLatency.add(duration);
        
        const isRateLimited = response.status === 429;
        const isQuotaExceeded = response.status === 402 || 
                                (response.status === 403 && 
                                 response.body.includes('quota'));
        
        quotaBurstRateLimited.add(isRateLimited || isQuotaExceeded);
        
        if (isRateLimited) {
            rateLimitedRequests.add(1);
        }
        
        if (isQuotaExceeded) {
            quotaExceededRequests.add(1);
        }
        
        check(response, {
            'quota burst response received': (r) => r.status >= 200 && r.status < 600,
            'quota burst rate limited or quota exceeded': (r) => 
                r.status === 429 || r.status === 402 || r.status === 403 || r.status === 200,
            'quota burst response time < 3s': (r) => duration < 3000,
        });
    });
}

// Setup function
export function setup() {
    console.log('Starting production load test...');
    console.log(`Base URL: ${BASE_URL}`);
    console.log(`Gateway URL: ${GATEWAY_URL}`);
    console.log(`MCP URL: ${MCP_URL}`);
    return {};
}

// Teardown function
export function teardown(data) {
    console.log('Load test completed');
}

// Handle summary
export function handleSummary(data) {
    return {
        'k6_results.json': JSON.stringify(data),
        stdout: textSummary(data, { indent: ' ', enableColors: true }),
    };
}

function textSummary(data, options) {
    const indent = options.indent || '';
    const enableColors = options.enableColors || false;

    let summary = '\n' + indent + '=== Load Test Summary ===\n\n';

    // Scenarios
    summary += indent + 'Scenarios:\n';
    for (const [name, scenario] of Object.entries(data.metrics.scenarios || {})) {
        summary += indent + `  ${name}: ${scenario.values.iterations} iterations\n`;
    }

    // Key metrics
    summary += '\n' + indent + 'Key Metrics:\n';
    summary += indent + `  Total Requests: ${data.metrics.total_requests?.values.count || 0}\n`;
    summary += indent + `  Failed Requests: ${data.metrics.http_req_failed?.values.rate || 0}\n`;
    summary += indent + `  Chat Error Rate: ${data.metrics.chat_errors?.values.rate || 0}\n`;
    summary += indent + `  RAG Error Rate: ${data.metrics.rag_errors?.values.rate || 0}\n`;
    summary += indent + `  MCP Error Rate: ${data.metrics.mcp_errors?.values.rate || 0}\n`;
    summary += indent + `  Adaptive Error Rate: ${data.metrics.adaptive_errors?.values.rate || 0}\n`;
    summary += indent + `  Rate Limited Requests: ${data.metrics.rate_limited_requests?.values.count || 0}\n`;
    summary += indent + `  Quota Exceeded Requests: ${data.metrics.quota_exceeded_requests?.values.count || 0}\n`;
    summary += indent + `  Quota Burst Rate Limited: ${(data.metrics.quota_burst_rate_limited?.values.rate * 100 || 0).toFixed(2)}%\n`;

    // Latencies
    summary += '\n' + indent + 'Latencies (ms):\n';
    if (data.metrics.http_req_duration) {
        const d = data.metrics.http_req_duration.values;
        summary += indent + `  Overall P50: ${d['p(50)'].toFixed(2)}\n`;
        summary += indent + `  Overall P95: ${d['p(95)'].toFixed(2)}\n`;
        summary += indent + `  Overall P99: ${d['p(99)'].toFixed(2)}\n`;
    }

    // SLO compliance
    summary += '\n' + indent + 'SLO Compliance:\n';
    const p99 = data.metrics.http_req_duration?.values['p(99)'] || 0;
    const errorRate = data.metrics.http_req_failed?.values.rate || 0;
    const availability = (1 - errorRate) * 100;

    summary += indent + `  Error Rate < 0.5%: ${errorRate < 0.005 ? 'PASS' : 'FAIL'} (${(errorRate * 100).toFixed(3)}%)\n`;
    summary += indent + `  P99 Latency < 2s: ${p99 < 2000 ? 'PASS' : 'FAIL'} (${p99.toFixed(2)}ms)\n`;
    summary += indent + `  Availability > 99.5%: ${availability >= 99.5 ? 'PASS' : 'FAIL'} (${availability.toFixed(2)}%)\n`;

    return summary;
}
