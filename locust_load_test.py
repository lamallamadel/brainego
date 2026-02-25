"""
Locust Load Testing for Production Validation
50 concurrent users with mixed workload (Chat, RAG, MCP)

Run:
    locust -f locust_load_test.py --host=http://localhost:8000 --users=50 --spawn-rate=5
"""

import json
import random
import time
from typing import Dict, List

from locust import HttpUser, TaskSet, task, between, events
from locust.runners import MasterRunner, WorkerRunner

# Custom metrics for SLO tracking
request_latencies = []
error_counts = {'chat': 0, 'rag': 0, 'mcp': 0}
total_counts = {'chat': 0, 'rag': 0, 'mcp': 0}


class ChatTasks(TaskSet):
    """Chat completion tasks"""

    chat_messages = [
        [{'role': 'user', 'content': 'What is machine learning?'}],
        [{'role': 'user', 'content': 'Explain neural networks in simple terms.'}],
        [{'role': 'user', 'content': 'How do I implement a REST API in Python?'}],
        [{'role': 'user', 'content': 'What are the best practices for code review?'}],
        [{'role': 'user', 'content': 'Describe the SOLID principles.'}],
        [{'role': 'user', 'content': 'How does containerization work?'}],
        [{'role': 'user', 'content': 'What is the difference between SQL and NoSQL?'}],
        [{'role': 'user', 'content': 'Explain microservices architecture.'}],
    ]

    @task(5)
    def chat_completion(self):
        """Send chat completion request"""
        messages = random.choice(self.chat_messages)
        payload = {
            'model': 'llama-3.3-8b-instruct',
            'messages': messages,
            'max_tokens': 150,
            'temperature': 0.7,
        }

        start_time = time.time()
        with self.client.post(
            '/v1/chat/completions',
            json=payload,
            catch_response=True,
            name='chat_completion',
        ) as response:
            latency = (time.time() - start_time) * 1000
            request_latencies.append(latency)
            total_counts['chat'] += 1

            if response.status_code == 200:
                try:
                    data = response.json()
                    if 'choices' in data and len(data['choices']) > 0:
                        response.success()
                        
                        # Check SLO: P99 < 2s
                        if latency > 2000:
                            response.failure(f'Latency exceeded 2s: {latency:.0f}ms')
                    else:
                        error_counts['chat'] += 1
                        response.failure('No choices in response')
                except json.JSONDecodeError:
                    error_counts['chat'] += 1
                    response.failure('Invalid JSON response')
            else:
                error_counts['chat'] += 1
                response.failure(f'Status {response.status_code}')

    @task(2)
    def chat_with_context(self):
        """Send chat with context"""
        messages = [
            {'role': 'system', 'content': 'You are a helpful coding assistant.'},
            {'role': 'user', 'content': 'How do I write a function in Python?'},
        ]
        payload = {
            'model': 'llama-3.3-8b-instruct',
            'messages': messages,
            'max_tokens': 200,
            'temperature': 0.7,
        }

        start_time = time.time()
        with self.client.post(
            '/v1/chat/completions',
            json=payload,
            catch_response=True,
            name='chat_with_context',
        ) as response:
            latency = (time.time() - start_time) * 1000
            request_latencies.append(latency)
            total_counts['chat'] += 1

            if response.status_code == 200:
                response.success()
            else:
                error_counts['chat'] += 1
                response.failure(f'Status {response.status_code}')


class RAGTasks(TaskSet):
    """RAG query and ingestion tasks"""

    queries = [
        'How do I deploy this application?',
        'What are the configuration options?',
        'Explain the architecture of the system',
        'What dependencies does this project have?',
        'How do I run the tests?',
        'What is the API documentation?',
        'How do I contribute to this project?',
        'What are the security best practices?',
    ]

    @task(7)
    def rag_query(self):
        """Query RAG system"""
        query = random.choice(self.queries)
        payload = {
            'query': query,
            'top_k': 5,
        }

        # Use gateway URL for RAG
        start_time = time.time()
        with self.client.post(
            'http://localhost:9002/rag/query',
            json=payload,
            catch_response=True,
            name='rag_query',
        ) as response:
            latency = (time.time() - start_time) * 1000
            request_latencies.append(latency)
            total_counts['rag'] += 1

            if response.status_code == 200:
                try:
                    data = response.json()
                    if 'results' in data:
                        response.success()
                        
                        # Check SLO: P99 < 2s
                        if latency > 2000:
                            response.failure(f'Latency exceeded 2s: {latency:.0f}ms')
                    else:
                        error_counts['rag'] += 1
                        response.failure('No results in response')
                except json.JSONDecodeError:
                    error_counts['rag'] += 1
                    response.failure('Invalid JSON response')
            else:
                error_counts['rag'] += 1
                response.failure(f'Status {response.status_code}')

    @task(3)
    def rag_ingest(self):
        """Ingest document into RAG"""
        document = {
            'content': f'Test document {random.randint(1000, 9999)} generated at {time.time()}',
            'metadata': {
                'source': 'locust_test',
                'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ'),
                'type': 'test',
            },
        }
        payload = {
            'documents': [document],
        }

        start_time = time.time()
        with self.client.post(
            'http://localhost:9002/rag/ingest',
            json=payload,
            catch_response=True,
            name='rag_ingest',
        ) as response:
            latency = (time.time() - start_time) * 1000
            request_latencies.append(latency)
            total_counts['rag'] += 1

            if response.status_code == 200:
                response.success()
                
                # Check SLO: P99 < 2s
                if latency > 2000:
                    response.failure(f'Latency exceeded 2s: {latency:.0f}ms')
            else:
                error_counts['rag'] += 1
                response.failure(f'Status {response.status_code}')


class MCPTasks(TaskSet):
    """MCP integration tasks"""

    mcp_requests = [
        {'tool': 'filesystem', 'operation': 'list_directory', 'path': '/workspace'},
        {'tool': 'github', 'operation': 'get_repo_info', 'repo': 'test/repo'},
        {'tool': 'notion', 'operation': 'search_pages', 'query': 'documentation'},
        {'tool': 'filesystem', 'operation': 'read_file', 'path': '/workspace/test.txt'},
    ]

    @task(5)
    def mcp_execute(self):
        """Execute MCP operation"""
        request = random.choice(self.mcp_requests)

        start_time = time.time()
        with self.client.post(
            'http://localhost:9100/mcp/execute',
            json=request,
            catch_response=True,
            name='mcp_execute',
        ) as response:
            latency = (time.time() - start_time) * 1000
            request_latencies.append(latency)
            total_counts['mcp'] += 1

            if response.status_code in (200, 202):
                response.success()
                
                # Check SLO: P99 < 2s
                if latency > 2000:
                    response.failure(f'Latency exceeded 2s: {latency:.0f}ms')
            else:
                error_counts['mcp'] += 1
                response.failure(f'Status {response.status_code}')

    @task(2)
    def mcp_health_check(self):
        """Check MCP gateway health"""
        with self.client.get(
            'http://localhost:9100/health',
            catch_response=True,
            name='mcp_health',
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f'Status {response.status_code}')


class ProductionUser(HttpUser):
    """Production load test user with mixed workload"""
    
    wait_time = between(1, 3)
    
    # Task distribution: 50% chat, 30% RAG, 20% MCP
    tasks = {
        ChatTasks: 5,
        RAGTasks: 3,
        MCPTasks: 2,
    }


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Initialize test"""
    print('Starting production load test...')
    print(f'Host: {environment.host}')
    print('SLO Targets:')
    print('  - Availability: 99.5%')
    print('  - P99 Latency: < 2s')
    print('  - Zero data loss')


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Generate SLO report"""
    print('\n' + '=' * 60)
    print('Production Validation Results')
    print('=' * 60)
    
    # Calculate metrics
    if request_latencies:
        sorted_latencies = sorted(request_latencies)
        p50 = sorted_latencies[int(len(sorted_latencies) * 0.50)]
        p95 = sorted_latencies[int(len(sorted_latencies) * 0.95)]
        p99 = sorted_latencies[int(len(sorted_latencies) * 0.99)]
        
        print('\nLatency Metrics:')
        print(f'  P50: {p50:.2f}ms')
        print(f'  P95: {p95:.2f}ms')
        print(f'  P99: {p99:.2f}ms')
    
    # Calculate availability
    total_requests = sum(total_counts.values())
    total_errors = sum(error_counts.values())
    
    if total_requests > 0:
        error_rate = (total_errors / total_requests) * 100
        availability = 100 - error_rate
        
        print('\nAvailability Metrics:')
        print(f'  Total Requests: {total_requests}')
        print(f'  Failed Requests: {total_errors}')
        print(f'  Error Rate: {error_rate:.3f}%')
        print(f'  Availability: {availability:.3f}%')
        
        print('\nPer-Service Errors:')
        for service, count in error_counts.items():
            service_total = total_counts.get(service, 0)
            if service_total > 0:
                service_error_rate = (count / service_total) * 100
                print(f'  {service.upper()}: {count}/{service_total} ({service_error_rate:.2f}%)')
    
    # SLO compliance
    print('\nSLO Compliance:')
    slo_pass = True
    
    if request_latencies:
        if p99 < 2000:
            print('  ✓ P99 Latency < 2s: PASS')
        else:
            print(f'  ✗ P99 Latency < 2s: FAIL ({p99:.2f}ms)')
            slo_pass = False
    
    if total_requests > 0:
        if availability >= 99.5:
            print(f'  ✓ Availability ≥ 99.5%: PASS')
        else:
            print(f'  ✗ Availability ≥ 99.5%: FAIL ({availability:.3f}%)')
            slo_pass = False
    
    print('\n' + '=' * 60)
    if slo_pass:
        print('Overall Result: PASS ✓')
    else:
        print('Overall Result: FAIL ✗')
    print('=' * 60)
    
    # Save detailed results
    results = {
        'latencies': {
            'p50': p50 if request_latencies else 0,
            'p95': p95 if request_latencies else 0,
            'p99': p99 if request_latencies else 0,
        },
        'availability': availability if total_requests > 0 else 0,
        'total_requests': total_requests,
        'total_errors': total_errors,
        'error_counts': error_counts,
        'total_counts': total_counts,
        'slo_pass': slo_pass,
    }
    
    with open('locust_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    print('\nDetailed results saved to locust_results.json')
