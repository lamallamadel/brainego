# Circuit Breaker and Fallback Chain Implementation

## Overview

This implementation provides comprehensive resilience patterns for the AI platform, including:

1. **Circuit Breakers** on all inter-service calls (5s timeout, 3 failure threshold, 30s recovery)
2. **Fallback Chain**: MAX GPU → Ollama CPU → Cache → Degraded message
3. **Liveness/Readiness Probes** on all Kubernetes pods
4. **Graceful Shutdown** with 30s termination grace period

## Architecture

### Circuit Breaker Pattern

The circuit breaker pattern prevents cascading failures by monitoring service health and temporarily blocking requests to failing services.

#### States

1. **CLOSED**: Normal operation, requests pass through
2. **OPEN**: Service is failing, requests are rejected immediately
3. **HALF_OPEN**: Testing if service recovered, limited requests allowed

#### State Transitions

```
CLOSED --[3 failures]--> OPEN
OPEN --[30s elapsed]--> HALF_OPEN
HALF_OPEN --[2 successes]--> CLOSED
HALF_OPEN --[1 failure]--> OPEN
```

#### Configuration

```python
CircuitBreakerConfig(
    failure_threshold=3,        # Failures before opening
    timeout_seconds=5.0,        # Request timeout
    recovery_timeout_seconds=30.0,  # Time before trying half-open
    success_threshold=2         # Successes to close from half-open
)
```

### Fallback Chain

The fallback chain provides multiple tiers of service degradation:

```
Tier 1: MAX GPU (Primary)
   ↓ (on failure)
Tier 2: Ollama CPU (Secondary)
   ↓ (on failure)
Tier 3: Redis Cache (Tertiary)
   ↓ (on failure)
Tier 4: Degraded Message (Last resort)
```

Each tier is protected by its own circuit breaker.

#### Caching Strategy

- **Cache Key**: SHA256 hash of prompt + parameters
- **TTL**: 1 hour (3600 seconds)
- **Cache Hit**: Response served immediately
- **Cache Miss**: Fall through to degraded message

## Implementation Details

### Files Created

1. **circuit_breaker.py**: Core circuit breaker implementation
   - `CircuitBreaker` class
   - `CircuitBreakerRegistry` for managing multiple breakers
   - `CircuitBreakerConfig` for configuration
   - `CircuitBreakerError` exception

2. **fallback_chain.py**: Fallback chain orchestration
   - `FallbackChain` class
   - Multi-tier degradation logic
   - Redis caching integration
   - Statistics tracking

3. **helm/ai-platform/values-health-probes.yaml**: Health probe configurations
   - Liveness probes for all services
   - Readiness probes for all services
   - Startup probes for slow-starting services
   - Lifecycle hooks for graceful shutdown

4. **helm/ai-platform/templates/api-server-deployment-with-probes.yaml**: Example deployment with probes

### Integration Points

#### Agent Router

The `agent_router.py` has been updated to:
- Initialize circuit breakers for each model
- Wrap all HTTP calls with circuit breaker protection
- Track circuit breaker state in metrics
- Expose circuit breaker statistics

```python
# Circuit breaker wraps model calls
result = await circuit_breaker.call(make_request)
```

#### API Server

The `api_server.py` has been updated to:
- Import circuit breaker utilities
- Add `/circuit-breakers` endpoint for statistics
- Implement graceful shutdown with SIGTERM handling
- Wait for in-flight requests during shutdown

```python
# Graceful shutdown
@app.on_event("shutdown")
async def shutdown_event():
    shutdown_in_progress = True
    await asyncio.sleep(5)  # Wait for requests
    # Close connections
```

#### Gateway Service

The `gateway_service.py` has been updated to:
- Wrap MAX Serve calls with circuit breaker
- Add circuit breaker statistics endpoint
- Implement graceful shutdown
- Handle SIGTERM/SIGINT signals

```python
# Protected MAX Serve call
return await max_serve_breaker.call(make_request)
```

## Health Probes Configuration

### Liveness Probes

Check if the container is alive and should be restarted if failing.

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 30
  periodSeconds: 30
  timeoutSeconds: 10
  failureThreshold: 3
```

### Readiness Probes

Check if the container is ready to accept traffic.

```yaml
readinessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 20
  periodSeconds: 10
  timeoutSeconds: 5
  failureThreshold: 3
```

### Startup Probes

Give slow-starting containers time to initialize.

```yaml
startupProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 5
  failureThreshold: 20  # 100s total
```

## Graceful Shutdown

### Termination Grace Period

All pods have a 30-second grace period:

```yaml
terminationGracePeriodSeconds: 30
```

### PreStop Hook

Delays SIGTERM to allow graceful cleanup:

```yaml
lifecycle:
  preStop:
    exec:
      command: ["/bin/sh", "-c", "sleep 5 && pkill -SIGTERM python"]
```

### Signal Handling

Python services handle SIGTERM/SIGINT:

```python
def handle_sigterm(signum, frame):
    logger.info("Received SIGTERM, shutting down...")
    raise KeyboardInterrupt

signal.signal(signal.SIGTERM, handle_sigterm)
signal.signal(signal.SIGINT, handle_sigterm)
```

## Usage

### Using Circuit Breakers

```python
from circuit_breaker import get_circuit_breaker, CircuitBreakerConfig

# Get or create a circuit breaker
breaker = get_circuit_breaker(
    "my_service",
    CircuitBreakerConfig(
        failure_threshold=3,
        timeout_seconds=5.0,
        recovery_timeout_seconds=30.0
    )
)

# Use it to protect a call
async def my_function():
    # Your service call here
    pass

try:
    result = await breaker.call(my_function)
except CircuitBreakerError:
    # Handle circuit breaker open
    pass
```

### Using Fallback Chain

```python
from fallback_chain import FallbackChain
import redis

# Initialize fallback chain
redis_client = redis.Redis(host='localhost', port=6379)
chain = FallbackChain(
    max_gpu_endpoint="http://max-serve:8080",
    ollama_cpu_endpoint="http://ollama:11434",
    redis_client=redis_client,
    degraded_message="Service temporarily unavailable"
)

# Generate with automatic fallback
result = await chain.generate(
    prompt="Hello, world!",
    max_tokens=100
)

print(f"Response: {result['text']}")
print(f"Tier used: {result['tier_used']}")
print(f"Success: {result['success']}")
```

### Monitoring Circuit Breakers

```bash
# Get circuit breaker statistics
curl http://localhost:8000/circuit-breakers

# Response
{
  "circuit_breakers": {
    "max_gpu": {
      "state": "closed",
      "total_requests": 100,
      "total_successes": 95,
      "total_failures": 5,
      "total_timeouts": 2,
      "total_circuit_open_rejections": 0
    },
    "model_llama": {
      "state": "open",
      "last_failure_time": "2025-01-17T12:00:00Z",
      "current_failure_count": 3
    }
  }
}
```

## Kubernetes Deployment

### Apply Health Probes

Merge the health probe configuration:

```bash
# Merge values
helm upgrade ai-platform ./helm/ai-platform \
  -f helm/ai-platform/values.yaml \
  -f helm/ai-platform/values-health-probes.yaml \
  --namespace ai-platform
```

### Verify Probes

```bash
# Check pod status
kubectl get pods -n ai-platform

# Describe pod to see probe configuration
kubectl describe pod api-server-xxx -n ai-platform

# Check probe events
kubectl get events -n ai-platform --field-selector involvedObject.name=api-server-xxx
```

### Test Graceful Shutdown

```bash
# Delete a pod and watch graceful shutdown
kubectl delete pod api-server-xxx -n ai-platform

# Check logs for shutdown messages
kubectl logs api-server-xxx -n ai-platform --previous
```

## Metrics and Observability

### Prometheus Metrics

Circuit breakers automatically expose metrics:

```
# Circuit breaker state (1=closed, 0=open)
circuit_breaker_state{name="max_gpu"} 1

# Total requests through circuit breaker
circuit_breaker_requests_total{name="max_gpu"} 100

# Failed requests
circuit_breaker_failures_total{name="max_gpu"} 5

# Circuit breaker open rejections
circuit_breaker_rejections_total{name="max_gpu"} 0
```

### Grafana Dashboards

Add panels for:
- Circuit breaker state timeline
- Failure rate by service
- Fallback tier usage distribution
- Average request latency by tier

## Testing

### Unit Tests

```python
# Test circuit breaker transitions
async def test_circuit_breaker():
    breaker = CircuitBreaker("test", CircuitBreakerConfig(
        failure_threshold=2,
        timeout_seconds=1.0,
        recovery_timeout_seconds=5.0
    ))
    
    # Test CLOSED -> OPEN transition
    for i in range(3):
        try:
            await breaker.call(failing_function)
        except:
            pass
    
    assert breaker.state == CircuitState.OPEN
```

### Integration Tests

```bash
# Test fallback chain
python -m pytest tests/test_fallback_chain.py

# Test health probes
python -m pytest tests/test_health_probes.py

# Test graceful shutdown
python -m pytest tests/test_graceful_shutdown.py
```

### Load Tests

```bash
# Run load test with circuit breaker
python load_test.py --requests 1000 --concurrency 50

# Verify circuit breaker opened during overload
curl http://localhost:8000/circuit-breakers | jq '.circuit_breakers.max_gpu.state'
```

## Troubleshooting

### Circuit Breaker Stuck Open

If a circuit breaker is stuck open:

```python
from circuit_breaker import get_circuit_breaker

# Manually reset
breaker = get_circuit_breaker("service_name")
breaker.reset()
```

### High Fallback Rate

Check circuit breaker statistics:

```bash
curl http://localhost:8000/circuit-breakers | jq '.circuit_breakers'
```

Investigate underlying service health:

```bash
kubectl logs -n ai-platform max-serve-llama-xxx --tail=100
```

### Graceful Shutdown Timeout

If pods take longer than 30s to terminate:

1. Increase `terminationGracePeriodSeconds`
2. Reduce `preStopDelaySeconds`
3. Check for hanging connections in logs

## Best Practices

1. **Circuit Breaker Tuning**:
   - Start with conservative thresholds (3 failures)
   - Monitor false positives and adjust
   - Use longer recovery times for expensive operations

2. **Fallback Chain**:
   - Always provide a degraded message fallback
   - Cache successful responses
   - Monitor tier usage distribution

3. **Health Probes**:
   - Liveness: Check process health only
   - Readiness: Check dependencies
   - Use appropriate timeouts for your workload

4. **Graceful Shutdown**:
   - Wait for in-flight requests
   - Close database connections
   - Save state before exit

## Performance Impact

- Circuit breaker overhead: < 1ms per request
- Fallback chain overhead: < 5ms (cache hit), 5-10s (full chain)
- Health probe overhead: Minimal (1 request every 10-30s)
- Graceful shutdown delay: 5-30s

## Future Enhancements

1. **Adaptive Circuit Breakers**: Adjust thresholds based on error rates
2. **Distributed Circuit Breakers**: Share state across replicas
3. **Circuit Breaker Dashboard**: Real-time visualization
4. **Predictive Fallback**: Pre-emptively use fallback tiers
5. **A/B Testing**: Compare circuit breaker configurations
