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
const chatLatency = new Trend('chat_latency_ms');
const ragLatency = new Trend('rag_latency_ms');
const mcpLatency = new Trend('mcp_latency_ms');
const totalRequests = new Counter('total_requests');

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
    },
    thresholds: {
        'http_req_duration': ['p(99)<2000'],  // SLO: P99 < 2s
        'http_req_duration{scenario:chat}': ['p(95)<1500', 'p(99)<2000'],
        'http_req_duration{scenario:rag}': ['p(95)<1800', 'p(99)<2000'],
        'http_req_duration{scenario:mcp}': ['p(95)<1500', 'p(99)<2000'],
        'http_req_failed': ['rate<0.005'],  // SLO: 99.5% availability
        'chat_errors': ['rate<0.01'],
        'rag_errors': ['rate<0.01'],
        'mcp_errors': ['rate<0.01'],
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

    summary += indent + `  P99 Latency < 2s: ${p99 < 2000 ? 'PASS' : 'FAIL'} (${p99.toFixed(2)}ms)\n`;
    summary += indent + `  Availability > 99.5%: ${availability >= 99.5 ? 'PASS' : 'FAIL'} (${availability.toFixed(2)}%)\n`;

    return summary;
}
