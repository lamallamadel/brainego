# Pilot: Kong Rate Limit Exceeded Runbook

## Alert: KongRateLimitExceeded

**Severity**: Warning  
**Component**: Kong Gateway  
**Pilot Critical**: Yes

---

## Overview

This alert fires when Kong Gateway is rejecting requests due to rate limit violations (HTTP 429 responses). This indicates a consumer is exceeding their configured rate limit, which could be legitimate high traffic, a misconfigured client, or a potential abuse scenario.

---

## Quick Diagnosis (2 minutes)

### Check Current Rate Limit Status

```bash
# Check Kong metrics for 429 rate
curl http://prometheus:9090/api/v1/query --data-urlencode 'query=sum by (route, consumer) (rate(kong_http_requests_total{code="429"}[5m]))'

# Check specific route/consumer in Grafana
open http://localhost:3000/d/kong-dashboard
```

### Identify Affected Consumer

```bash
# Check which consumer is being rate limited
kubectl logs -l app=kong --tail=100 | grep "429"

# Check Kong admin API for consumer info
curl http://kong-admin:8001/consumers/{consumer_id}
```

---

## Investigation Steps

### Step 1: Verify Rate Limit Configuration

```bash
# Check rate limit plugin configuration for the route
curl http://kong-admin:8001/routes/{route_id}/plugins | jq '.[] | select(.name == "rate-limiting")'

# Expected output shows configured limits:
# {
#   "config": {
#     "minute": 100,
#     "hour": 5000,
#     "policy": "redis"
#   }
# }
```

### Step 2: Analyze Traffic Pattern

```bash
# Check request rate over time
curl http://prometheus:9090/api/v1/query --data-urlencode 'query=sum by (consumer) (rate(kong_http_requests_total[5m]))'

# Check if this is a spike or sustained high traffic
# Review last 1 hour of traffic in Grafana
```

### Step 3: Determine Root Cause

**Legitimate Traffic Spike?**
- Marketing campaign launched
- External event driving traffic
- Normal business growth

**Misconfigured Client?**
- Retry storm (exponential backoff not implemented)
- Client polling too aggressively
- Multiple instances using same API key

**Potential Abuse?**
- Unusual access patterns
- Traffic from unexpected sources
- Credential compromise

---

## Remediation

### Option 1: Increase Rate Limit (Legitimate Traffic)

```bash
# Update rate limit plugin configuration
curl -X PATCH http://kong-admin:8001/plugins/{plugin_id} \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "minute": 200,
      "hour": 10000
    }
  }'

# Verify change
curl http://kong-admin:8001/plugins/{plugin_id} | jq '.config'
```

### Option 2: Contact Consumer (Misconfiguration)

```bash
# Get consumer contact information
curl http://kong-admin:8001/consumers/{consumer_id} | jq '.custom_id, .tags'

# Check if consumer has multiple API keys (potential issue)
curl http://kong-admin:8001/consumers/{consumer_id}/key-auth | jq '.data | length'

# Temporarily increase limit while consumer fixes client
curl -X PATCH http://kong-admin:8001/plugins/{plugin_id} \
  -H "Content-Type: application/json" \
  -d '{"config": {"minute": 150}}'
```

### Option 3: Block Abusive Consumer (Security)

```bash
# Disable consumer account
curl -X PATCH http://kong-admin:8001/consumers/{consumer_id} \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'

# Or revoke specific API key
curl -X DELETE http://kong-admin:8001/consumers/{consumer_id}/key-auth/{key_id}

# Add IP to blocklist (if IP-based)
curl -X POST http://kong-admin:8001/plugins \
  -H "Content-Type: application/json" \
  -d '{
    "name": "ip-restriction",
    "config": {
      "deny": ["1.2.3.4"]
    }
  }'
```

### Option 4: Implement Request Queuing

```bash
# If using Kong Enterprise, enable request queuing
curl -X POST http://kong-admin:8001/plugins \
  -H "Content-Type: application/json" \
  -d '{
    "name": "request-queuing",
    "config": {
      "max_queue_size": 1000,
      "timeout": 60
    }
  }'
```

---

## Prevention

### 1. Set Appropriate Rate Limits

```yaml
# Rate limit tiers based on consumer type
consumers:
  free_tier:
    minute: 60
    hour: 3000
    day: 50000
  
  paid_tier:
    minute: 300
    hour: 15000
    day: 300000
  
  enterprise:
    minute: 1000
    hour: 60000
    day: 1000000
```

### 2. Implement Client-Side Rate Limiting

Provide SDKs/documentation for consumers:

```python
# Example: Python client with built-in rate limiting
from ratelimit import limits, sleep_and_retry

@sleep_and_retry
@limits(calls=90, period=60)  # 90 calls per minute (90% of limit)
def call_api(endpoint):
    response = requests.get(f"https://api.example.com/{endpoint}")
    return response.json()
```

### 3. Monitor Rate Limit Utilization

```yaml
# Prometheus alert for consumers approaching limits
- alert: ConsumerApproachingRateLimit
  expr: |
    (
      sum by (consumer) (rate(kong_http_requests_total[5m])) /
      kong_rate_limit_config{type="minute"} > 0.8
    )
  for: 5m
  labels:
    severity: info
  annotations:
    summary: "Consumer {{ $labels.consumer }} approaching rate limit"
```

### 4. Implement Retry-After Header

Ensure Kong returns `Retry-After` header in 429 responses:

```yaml
# Kong configuration
rate-limiting:
  config:
    policy: redis
    hide_client_headers: false
    retry_after_jitter_max: 2
```

### 5. Use Redis for Distributed Rate Limiting

```bash
# Configure Redis policy for accurate limits across Kong instances
curl -X PATCH http://kong-admin:8001/plugins/{plugin_id} \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "policy": "redis",
      "redis_host": "redis",
      "redis_port": 6379,
      "redis_database": 1
    }
  }'
```

---

## Related Alerts

- **KongRateLimitExceededCritical**: High volume of 429s (>50 req/s)
- **KongHighErrorRate**: Overall error rate spike
- **KongUpstreamConnectionFailures**: Backend service issues

---

## Escalation

- **Immediate (<5 min)**: On-call SRE
- **Within 1 hour**: API Product Manager (if legitimate traffic increase)
- **Security Team**: If suspected abuse/attack

---

**Version**: 1.0  
**Last Updated**: 2025-01-30  
**Owner**: SRE Team
