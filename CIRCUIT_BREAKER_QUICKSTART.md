# Circuit Breaker & Fallback Chain - Quick Start Guide

## Prerequisites

- Python 3.9+
- Redis (for caching)
- Kubernetes cluster (for deployment)
- Helm 3.0+

## Quick Setup

### 1. Install Dependencies

The circuit breaker implementation has no external dependencies beyond what's already in `requirements.txt`.

### 2. Basic Usage

#### Circuit Breaker

```python
from circuit_breaker import get_circuit_breaker, CircuitBreakerConfig

# Create a circuit breaker
breaker = get_circuit_breaker(
    "my_service",
    CircuitBreakerConfig(
        failure_threshold=3,      # Open after 3 failures
        timeout_seconds=5.0,      # 5 second timeout
        recovery_timeout_seconds=30.0  # Try again after 30s
    )
)

# Wrap async function calls
async def call_service():
    response = await httpx.get("http://my-service/api")
    return response.json()

try:
    result = await breaker.call(call_service)
    print(f"Success: {result}")
except CircuitBreakerError:
    print("Circuit breaker is open, service unavailable")
except Exception as e:
    print(f"Service call failed: {e}")
```

#### Fallback Chain

```python
from fallback_chain import FallbackChain
import redis

# Initialize
redis_client = redis.Redis(host='localhost', port=6379)
chain = FallbackChain(
    max_gpu_endpoint="http://localhost:8080",
    ollama_cpu_endpoint="http://localhost:11434",
    redis_client=redis_client
)

# Generate with automatic fallback
result = await chain.generate(
    prompt="Explain quantum computing",
    max_tokens=200
)

print(f"Response: {result['text']}")
print(f"Used tier: {result['tier_used']}")
```

### 3. View Statistics

```bash
# Check circuit breaker status
curl http://localhost:8000/circuit-breakers | jq

# Check fallback chain statistics
curl http://localhost:8000/metrics | jq '.metrics'
```

## Kubernetes Deployment

### 1. Apply Health Probe Configuration

```bash
helm upgrade ai-platform ./helm/ai-platform \
  -f helm/ai-platform/values.yaml \
  -f helm/ai-platform/values-health-probes.yaml \
  --namespace ai-platform \
  --create-namespace
```

### 2. Verify Deployment

```bash
# Check pod status
kubectl get pods -n ai-platform

# Check health probes
kubectl describe pod api-server-xxx -n ai-platform | grep -A 10 "Liveness\|Readiness"

# View logs
kubectl logs -f api-server-xxx -n ai-platform
```

### 3. Test Graceful Shutdown

```bash
# Delete a pod
kubectl delete pod api-server-xxx -n ai-platform

# Watch shutdown logs
kubectl logs api-server-xxx -n ai-platform --previous
```

## Docker Compose

### Update docker-compose.yaml

Circuit breakers and health probes are automatically enabled in the existing `docker-compose.yaml`.

### Start Services

```bash
# Start all services
docker compose up -d

# View logs
docker compose logs -f api-server

# Check health
curl http://localhost:8000/health
curl http://localhost:8000/circuit-breakers
```

### Test Fallback Chain

```bash
# Stop MAX GPU service
docker compose stop max-serve-llama

# Make a request (should fallback to Ollama or cache)
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Hello"}],
    "max_tokens": 50
  }'

# Check which tier was used
curl http://localhost:8000/metrics | jq
```

## Configuration Options

### Circuit Breaker Config

```python
CircuitBreakerConfig(
    failure_threshold=3,        # Failures before opening (default: 3)
    timeout_seconds=5.0,        # Request timeout (default: 5.0)
    recovery_timeout_seconds=30.0,  # Recovery time (default: 30.0)
    success_threshold=2         # Successes to close (default: 2)
)
```

### Fallback Chain Config

```python
FallbackChain(
    max_gpu_endpoint="http://max-serve:8080",
    ollama_cpu_endpoint="http://ollama:11434",  # Optional
    redis_client=redis.Redis(...),              # Optional
    degraded_message="Service temporarily unavailable"
)
```

### Health Probe Config

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 30
  periodSeconds: 30
  timeoutSeconds: 10
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 20
  periodSeconds: 10
  timeoutSeconds: 5
  failureThreshold: 3
```

## Common Scenarios

### 1. Service Temporarily Down

```
Request → Circuit Breaker (CLOSED)
       → MAX GPU fails (timeout)
       → Circuit Breaker (1 failure)
       → Retry → MAX GPU fails
       → Circuit Breaker (2 failures)
       → Retry → MAX GPU fails
       → Circuit Breaker (3 failures) → OPEN
       → Reject subsequent requests immediately
```

### 2. Fallback Chain Activation

```
Request → MAX GPU (circuit open)
       → Ollama CPU (success)
       → Cache response
       → Return to client
```

### 3. Graceful Pod Restart

```
SIGTERM received
  → PreStop hook (sleep 5s)
  → Stop accepting new requests
  → Wait for in-flight requests
  → Close connections
  → Exit (within 30s grace period)
```

## Testing

### Unit Test Circuit Breaker

```python
import pytest
from circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitState

@pytest.mark.asyncio
async def test_circuit_breaker_opens():
    breaker = CircuitBreaker("test", CircuitBreakerConfig(
        failure_threshold=2,
        timeout_seconds=1.0
    ))
    
    async def failing_call():
        raise Exception("Service down")
    
    # First 2 failures
    for _ in range(2):
        try:
            await breaker.call(failing_call)
        except:
            pass
    
    # Circuit should be OPEN
    assert breaker.state == CircuitState.OPEN
```

### Integration Test Fallback

```python
@pytest.mark.asyncio
async def test_fallback_chain():
    chain = FallbackChain(
        max_gpu_endpoint="http://fake-endpoint",
        degraded_message="Test degraded"
    )
    
    result = await chain.generate("test prompt")
    
    # Should fall back to degraded message
    assert result['tier_used'] == 'degraded'
    assert result['text'] == "Test degraded"
```

### Load Test

```bash
# Install k6 or use existing load_test.py
python load_test.py --requests 1000 --concurrency 50

# Check circuit breaker metrics
curl http://localhost:8000/circuit-breakers
```

## Monitoring

### Prometheus Queries

```promql
# Circuit breaker state
circuit_breaker_state{name="max_gpu"}

# Request rate
rate(circuit_breaker_requests_total[5m])

# Failure rate
rate(circuit_breaker_failures_total[5m]) / rate(circuit_breaker_requests_total[5m])

# Rejection rate (circuit open)
rate(circuit_breaker_rejections_total[5m])
```

### Grafana Dashboard

Import dashboard JSON (to be created):

```bash
# Create dashboard from template
kubectl apply -f configs/grafana/dashboards/circuit-breaker-dashboard.json
```

## Troubleshooting

### Circuit Breaker Won't Close

**Symptoms**: Circuit remains OPEN even after service recovery

**Solutions**:
```python
# Check current state
curl http://localhost:8000/circuit-breakers | jq '.circuit_breakers.max_gpu'

# Manually reset
from circuit_breaker import get_circuit_breaker
breaker = get_circuit_breaker("max_gpu")
breaker.reset()
```

### High Latency

**Symptoms**: Requests taking longer than expected

**Check**:
1. Circuit breaker timeout settings
2. Network latency to services
3. Fallback tier performance

```bash
# Check metrics
curl http://localhost:8000/metrics | jq '.metrics.p95_latency_ms'
```

### Pods Not Starting

**Symptoms**: Pods stuck in CrashLoopBackOff

**Check**:
1. Startup probe failure threshold
2. Service dependencies (Redis, Qdrant, etc.)
3. Application logs

```bash
kubectl logs -n ai-platform api-server-xxx
kubectl describe pod -n ai-platform api-server-xxx
```

## Next Steps

1. **Read Full Documentation**: See `CIRCUIT_BREAKER_IMPLEMENTATION.md`
2. **Configure Prometheus**: Set up alerting on circuit breaker events
3. **Tune Parameters**: Adjust thresholds based on your workload
4. **Monitor Metrics**: Track fallback usage and circuit breaker state
5. **Load Test**: Verify behavior under high load

## Support

For issues or questions:
- Check logs: `kubectl logs -n ai-platform <pod-name>`
- View metrics: `curl http://localhost:8000/circuit-breakers`
- Review documentation: `CIRCUIT_BREAKER_IMPLEMENTATION.md`
