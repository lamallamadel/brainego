# Chaos Engineering Implementation

## Overview

This implementation extends the chaos engineering test suite with advanced tests for network partitions, memory pressure, and database failover, along with comprehensive Prometheus metrics and alerts.

## Files Modified

### 1. `chaos_engineering.py`
Extended with three new advanced chaos tests:

#### `network_partition_test()`
- **Purpose**: Simulate 50% packet loss between api-server and Qdrant for 60s
- **Implementation**:
  - Uses `tc` (traffic control) with `netem` to add 50% packet loss
  - Auto-installs `iproute2` package if not available
  - Monitors circuit breaker activation via health endpoint
  - Records `network_partition_active` metric in Prometheus
- **Verification**: 
  - Circuit breaker triggers degraded mode
  - Service recovers after partition is removed
  - No data loss or corruption

#### `memory_pressure_test()`
- **Purpose**: Simulate 90% memory usage on learning-engine pod
- **Implementation**:
  - Uses `stress-ng` to consume 90% of container memory limit
  - Auto-installs `stress-ng` if not available
  - Calculates target memory based on container limits
  - Monitors for graceful degradation signals
- **Verification**:
  - Service stays responsive but degraded
  - No OOM kills or crashes
  - Automatic recovery after pressure is released

#### `database_failover_test()`
- **Purpose**: Kill Postgres primary and verify StatefulSet automatic recovery
- **Implementation**:
  - Kills the Postgres container using Docker API
  - Monitors for automatic pod restart (StatefulSet behavior)
  - Waits up to 120s for recovery
  - Verifies database accepts connections after restart
- **Verification**:
  - StatefulSet automatically restarts the pod
  - Database recovers and accepts connections
  - No data loss or corruption

### 2. `run_production_validation.py`
Added `--chaos` flag to run advanced chaos tests:

```python
python run_production_validation.py --chaos
```

- New `chaos_advanced` parameter in `ProductionValidator` class
- Updated `run_chaos_engineering()` to accept `advanced` flag
- Passes flag to `chaos_engineering.py` subprocess

### 3. `circuit_breaker.py`
Added Prometheus metrics export:

**New Metrics**:
- `circuit_breaker_state`: Gauge (0=closed, 1=open, 2=half_open)
- `circuit_breaker_requests_total`: Counter
- `circuit_breaker_rejections_total`: Counter
- `circuit_breaker_failures_total`: Counter
- `circuit_breaker_successes_total`: Counter
- `circuit_breaker_timeouts_total`: Counter

**Labels**: `name`, `service`

**Updates**:
- All state transitions update the `circuit_breaker_state` gauge
- All requests/rejections/failures/successes/timeouts increment respective counters
- Optional dependency on `prometheus_client` (graceful degradation if not available)

### 4. `metrics_exporter.py`
Extended with chaos engineering and circuit breaker metrics:

**New Methods**:
- `update_circuit_breaker_state()`: Update circuit breaker state gauge
- `record_circuit_breaker_request()`: Record request counter
- `record_circuit_breaker_rejection()`: Record rejection counter
- `record_circuit_breaker_failure()`: Record failure counter
- `record_circuit_breaker_success()`: Record success counter
- `record_circuit_breaker_timeout()`: Record timeout counter
- `record_chaos_test()`: Record chaos test execution
- `record_chaos_test_failure()`: Record chaos test failure
- `set_network_partition()`: Set network partition active/inactive

### 5. `configs/prometheus/rules/alerts.yml`
Added new alert group `chaos_engineering_alerts` with 13 alerts:

#### Circuit Breaker Alerts
- **CircuitBreakerOpen**: Circuit breaker in OPEN state for 2+ minutes (warning)
- **CircuitBreakerOpenExtended**: Circuit breaker OPEN for 10+ minutes (critical)
- **CircuitBreakerHighRejectionRate**: >50% rejection rate (warning)

#### Pod Restart Alerts
- **PodRestartRateHigh**: Restart rate > 0.1/sec over 15m (warning)
- **PodRestartRateCritical**: Restart rate > 0.3/sec (critical)
- **PodRestartSpike**: 3+ restarts in 10 minutes (critical)
- **PodCrashLoopBackOff**: Pod in CrashLoopBackOff for 5+ minutes (critical)
- **PodNotReady**: Pod not ready for 5+ minutes (warning)

#### Database Alerts
- **StatefulSetPodDown**: StatefulSet has pods not ready for 5+ minutes (critical)

#### Chaos Test Alerts
- **ChaosTestHighFailureRate**: >25% failure rate during testing (warning)
- **NetworkPartitionDetected**: Active network partition detected (warning)
- **MemoryPressureDetected**: Container using >90% of memory limit (warning)

## Prometheus Metrics

### Circuit Breaker Metrics
```prometheus
# Gauge: 0=closed, 1=open, 2=half_open
circuit_breaker_state{name="qdrant-client", service="api-server"}

# Counters
circuit_breaker_requests_total{name="qdrant-client", service="api-server"}
circuit_breaker_rejections_total{name="qdrant-client", service="api-server"}
circuit_breaker_failures_total{name="qdrant-client", service="api-server"}
circuit_breaker_successes_total{name="qdrant-client", service="api-server"}
circuit_breaker_timeouts_total{name="qdrant-client", service="api-server"}
```

### Chaos Test Metrics
```prometheus
# Counters
chaos_test_total{test_type="network_partition"}
chaos_test_total{test_type="memory_pressure"}
chaos_test_total{test_type="database_failover"}

chaos_test_failures_total{test_type="network_partition", service="api-server"}
chaos_test_failures_total{test_type="memory_pressure", service="learning-engine"}
chaos_test_failures_total{test_type="database_failover", service="postgres"}

# Gauge: 0=inactive, 1=active
network_partition_active{source="api-server", target="qdrant"}
```

## Usage

### Run Chaos Tests Standalone

```bash
# Basic tests only (random pod kill, CPU saturation, network partition, memory pressure)
python chaos_engineering.py

# Basic + advanced tests (includes network_partition_test, memory_pressure_test, database_failover_test)
python chaos_engineering.py --advanced
```

### Run via Production Validation

```bash
# Full production validation with advanced chaos tests
python run_production_validation.py --full --chaos

# Quick validation without k6, but with advanced chaos tests
python run_production_validation.py --quick --chaos
```

## Test Scenarios

### Network Partition Test
1. Gets api-server and qdrant containers
2. Installs `iproute2` (tc) if not available
3. Adds 50% packet loss using `tc qdisc add dev eth0 root netem loss 50%`
4. Sets `network_partition_active{source="api-server", target="qdrant"}=1`
5. Monitors for circuit breaker activation (polls `/health/circuit-breakers` endpoint)
6. Waits 60 seconds
7. Removes packet loss using `tc qdisc del dev eth0 root netem`
8. Sets `network_partition_active{source="api-server", target="qdrant"}=0`
9. Waits 90 seconds for recovery
10. Verifies api-server is healthy and circuit breaker functioned

### Memory Pressure Test
1. Gets learning-engine container
2. Installs `stress-ng` if not available
3. Gets container memory limit from Docker stats
4. Calculates 90% of memory limit
5. Starts `stress-ng --vm 1 --vm-bytes <90%>M --timeout 90s`
6. Monitors for graceful degradation signals (polls `/health` endpoint)
7. Waits 90 seconds
8. Kills remaining stress processes
9. Waits 60 seconds for recovery
10. Verifies container is healthy

### Database Failover Test
1. Gets postgres container
2. Records initial container ID
3. Kills the postgres container
4. Waits 10 seconds
5. Monitors for automatic recovery (polls for container restart)
6. Waits up to 120 seconds for recovery
7. Verifies postgres is running and accepting connections (`pg_isready`)

## Alert Configuration

All alerts are defined in `configs/prometheus/rules/alerts.yml` under the `chaos_engineering_alerts` group with 30s evaluation interval.

### Alert Severity Levels
- **Critical**: Immediate action required (e.g., CrashLoopBackOff, StatefulSet pod down)
- **Warning**: Investigation needed (e.g., circuit breaker open, high restart rate)

### Alert Labels
All chaos alerts include:
- `severity`: warning or critical
- `component`: circuit-breaker, kubernetes, or chaos-engineering

### Alert Annotations
All alerts include:
- `summary`: Brief description
- `description`: Detailed information with metric values

## Dependencies

### Required
- `docker`: Python Docker SDK for container manipulation
- Docker daemon access

### Optional (Auto-installed)
- `iproute2`: For traffic control (tc) - auto-installed in containers
- `stress-ng`: For memory pressure - auto-installed in containers
- `prometheus_client`: For metrics export - gracefully degrades if not available

## Validation

After running chaos tests:

1. Check `chaos_report.json` for detailed results
2. Check Prometheus for metrics:
   ```promql
   circuit_breaker_state{state="open"}
   rate(chaos_test_failures_total[5m])
   network_partition_active
   ```
3. Check Alertmanager for triggered alerts
4. Verify services recovered successfully

## Integration with CI/CD

Chaos tests can be integrated into CI/CD pipelines:

```yaml
# GitHub Actions example
- name: Run Chaos Tests
  run: python chaos_engineering.py --advanced
  
- name: Check Resilience Score
  run: |
    SCORE=$(jq -r '.resilience_score' chaos_report.json)
    if [ "$SCORE" -lt 90 ]; then
      echo "Resilience score below threshold: $SCORE%"
      exit 1
    fi
```

## Troubleshooting

### tc command not found
- The test auto-installs `iproute2` package
- If installation fails, install manually: `apt-get install -y iproute2` or `apk add iproute2`

### stress-ng command not found
- The test auto-installs `stress-ng` package
- If installation fails, install manually: `apt-get install -y stress-ng` or `apk add stress-ng`

### Circuit breaker not triggering
- Check circuit breaker configuration in api-server
- Verify health endpoint exists: `curl http://localhost:8000/health/circuit-breakers`
- Increase packet loss percentage if needed

### Container not recovering
- Check Docker restart policy
- For StatefulSets, verify Kubernetes is managing the pod
- Check resource limits and quotas

## Future Enhancements

- [ ] Add latency injection (delay packets instead of dropping)
- [ ] Add disk I/O pressure tests
- [ ] Add network bandwidth throttling
- [ ] Add cascading failure tests (multiple services)
- [ ] Add gradual degradation tests (slowly increasing load)
- [ ] Add recovery time measurement and SLO validation
- [ ] Add automated rollback on chaos test failures
- [ ] Add chaos test scheduling (periodic execution)
