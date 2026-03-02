# Debug Memory Leak Playbook

## Table of Contents
1. [Overview](#overview)
2. [Quick Diagnosis](#quick-diagnosis)
3. [Investigation Steps](#investigation-steps)
4. [Common Causes and Solutions](#common-causes-and-solutions)
5. [Mitigation Strategies](#mitigation-strategies)
6. [Prevention](#prevention)

---

## Overview

This playbook guides you through investigating and resolving memory leaks in the AI Platform.

### Memory Thresholds

| Metric | Normal | Warning | Critical |
|--------|--------|---------|----------|
| Memory Usage | <70% | 70-85% | >85% |
| Memory Growth Rate | <1% per hour | 1-5% per hour | >5% per hour |
| OOM Kills | 0 | 0 | >0 |

### Symptoms

- Gradual memory usage increase over time
- OOM (Out Of Memory) kills
- Pod/container restarts due to memory
- Slow performance degradation
- Alert fired: `MemoryLeakDetected` or `HighMemoryUsage`

---

## Quick Diagnosis

### Step 1: Verify Memory Leak (5 minutes)

```bash
# Check current memory usage
kubectl top pods -n production --sort-by=memory

# Check memory over time (Grafana)
open http://localhost:3000/d/platform-overview

# Quick Prometheus query for memory trend
curl -s 'http://localhost:9090/api/v1/query?query=container_memory_usage_bytes{namespace="production",pod=~"api-server.*"}' | jq

# Check for OOM kills
kubectl get events -n production | grep OOM

# Check restart count (high restart count indicates repeated OOM)
kubectl get pods -n production -o wide | grep api-server
```

### Step 2: Identify Affected Service (3 minutes)

```bash
# List all services by memory usage
kubectl top pods -n production --sort-by=memory | head -20

# Check memory limits
kubectl describe pod <pod-name> -n production | grep -A 5 "Limits:"

# Calculate memory growth rate
# Compare current vs 1 hour ago
memory_now=$(kubectl top pod <pod-name> -n production | awk 'NR==2 {print $3}')
echo "Current memory: $memory_now"
# Check Grafana for historical data
```

### Step 3: Quick Assessment (2 minutes)

**Questions to Answer**:
- Is memory growing linearly over time?
- Does memory grow with request volume?
- Does memory reset after pod restart?
- Are there specific operations that trigger growth?

```bash
# Check if memory correlates with request rate
curl -s 'http://localhost:9090/api/v1/query?query=rate(http_requests_total[5m])' | jq

# Check recent changes (deployments, config)
kubectl rollout history deployment/api-server -n production
```

---

## Investigation Steps

### Phase 1: Container-Level Analysis

#### 1.1 Monitor Memory Usage Trend

```bash
# Watch memory usage in real-time
watch -n 10 'kubectl top pod <pod-name> -n production'

# Or use docker stats
docker stats --no-stream <container-id>

# Check memory metrics
curl http://localhost:8000/metrics | grep memory
```

#### 1.2 Check Memory Breakdown

```bash
# Get detailed memory stats from cgroups
kubectl exec -it <pod-name> -n production -- cat /sys/fs/cgroup/memory/memory.stat

# Key metrics:
# - rss: Resident Set Size (actual RAM used)
# - cache: Page cache
# - mapped_file: Memory-mapped files
# - inactive_anon: Memory that can be swapped

# Or using Docker
docker exec <container-id> cat /sys/fs/cgroup/memory/memory.stat
```

#### 1.3 Inspect Process Memory

```bash
# Get process memory map
kubectl exec -it <pod-name> -n production -- ps aux

# For Python processes
kubectl exec -it <pod-name> -n production -- python -c "
import psutil
import os
process = psutil.Process(os.getpid())
print('Memory Info:', process.memory_info())
print('Memory Percent:', process.memory_percent())
"
```

---

### Phase 2: Application-Level Analysis

#### 2.1 Python Memory Profiling

**Install memory profiler (if not in image)**:

```bash
# Add to Dockerfile or install at runtime
kubectl exec -it <pod-name> -n production -- pip install memory-profiler
```

**Profile specific function**:

```python
# Add @profile decorator to suspected functions
from memory_profiler import profile

@profile
def process_inference(request):
    # Your code here
    pass
```

**Run profiler**:

```bash
# Run with memory profiler
kubectl exec -it <pod-name> -n production -- python -m memory_profiler api_server.py

# Or use tracemalloc (built-in)
kubectl exec -it <pod-name> -n production -- python -c "
import tracemalloc
tracemalloc.start()

# Run some operations
# ...

snapshot = tracemalloc.take_snapshot()
top_stats = snapshot.statistics('lineno')

for stat in top_stats[:10]:
    print(stat)
"
```

#### 2.2 Object Reference Analysis

```bash
# Check Python object counts
kubectl exec -it <pod-name> -n production -- python -c "
import gc
import sys

# Get object counts by type
from collections import Counter
types = Counter(type(obj).__name__ for obj in gc.get_objects())
for obj_type, count in types.most_common(20):
    print(f'{obj_type}: {count}')
"

# Check for circular references
kubectl exec -it <pod-name> -n production -- python -c "
import gc
gc.collect()
print('Uncollectable:', gc.garbage)
"
```

#### 2.3 Heap Dump Analysis

**For Python (using guppy3)**:

```bash
# Install guppy3 (if not in image)
kubectl exec -it <pod-name> -n production -- pip install guppy3

# Take heap snapshot
kubectl exec -it <pod-name> -n production -- python -c "
from guppy import hpy
h = hpy()
print(h.heap())
"
```

**For Python (using objgraph)**:

```bash
# Install objgraph
kubectl exec -it <pod-name> -n production -- pip install objgraph

# Find memory leaks
kubectl exec -it <pod-name> -n production -- python -c "
import objgraph
import gc

gc.collect()
objgraph.show_most_common_types(limit=20)

# Show growth
objgraph.show_growth()
"
```

#### 2.4 Check for Common Python Memory Issues

```bash
# Check for large global variables
kubectl exec -it <pod-name> -n production -- python -c "
import sys
globals_list = [(name, sys.getsizeof(obj)) for name, obj in globals().items()]
globals_list.sort(key=lambda x: x[1], reverse=True)
for name, size in globals_list[:10]:
    print(f'{name}: {size} bytes')
"

# Check for unclosed files
kubectl exec -it <pod-name> -n production -- lsof -p <pid> | wc -l

# Check for unclosed database connections
kubectl logs <pod-name> -n production | grep -i "connection" | tail -50
```

---

### Phase 3: External Resource Analysis

#### 3.1 Database Connection Leaks

```bash
# Check PostgreSQL connections from application
docker exec postgres psql -U ai_user -d ai_platform -c "
  SELECT count(*), application_name, state 
  FROM pg_stat_activity 
  WHERE application_name = 'ai-platform-api'
  GROUP BY application_name, state;
"

# Check for idle connections (potential leak)
docker exec postgres psql -U ai_user -d ai_platform -c "
  SELECT pid, state, state_change, query 
  FROM pg_stat_activity 
  WHERE state = 'idle' 
  AND state_change < now() - interval '10 minutes';
"

# Check connection pool metrics
curl http://localhost:8000/metrics | grep db_pool
```

**Solution for connection leaks**:

```python
# Bad: Connection not closed
def get_data():
    conn = psycopg2.connect(...)
    cursor = conn.cursor()
    cursor.execute("SELECT ...")
    return cursor.fetchall()
    # Connection never closed!

# Good: Use context manager
def get_data():
    with psycopg2.connect(...) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT ...")
            return cursor.fetchall()
    # Connection automatically closed
```

#### 3.2 HTTP Client Leaks

```bash
# Check for open HTTP connections
kubectl exec -it <pod-name> -n production -- netstat -an | grep ESTABLISHED | wc -l

# Check for connection pool leaks
curl http://localhost:8000/metrics | grep http_client_pool

# Check application logs for connection warnings
kubectl logs <pod-name> -n production | grep -i "connection\|timeout\|pool"
```

**Solution for HTTP client leaks**:

```python
# Bad: Session not closed
import requests

def fetch_data():
    session = requests.Session()
    response = session.get('http://api.example.com')
    return response.json()
    # Session never closed!

# Good: Use context manager
import httpx

async def fetch_data():
    async with httpx.AsyncClient() as client:
        response = await client.get('http://api.example.com')
        return response.json()
    # Client automatically closed
```

#### 3.3 Cache Memory Leaks

```bash
# Check cache size
curl http://localhost:8000/metrics | grep cache_size

# Check cache eviction rate
curl http://localhost:8000/metrics | grep cache_evictions

# Inspect cache contents
kubectl exec -it <pod-name> -n production -- python -c "
from api_server import cache  # Adjust import
print('Cache size:', len(cache))
print('Cache memory:', sys.getsizeof(cache))
"
```

**Solution for cache leaks**:

```python
# Implement proper cache eviction
from functools import lru_cache

# Bad: Unbounded cache
cache = {}

def get_user(user_id):
    if user_id not in cache:
        cache[user_id] = fetch_user(user_id)
    return cache[user_id]

# Good: Bounded cache with LRU eviction
@lru_cache(maxsize=1000)
def get_user(user_id):
    return fetch_user(user_id)

# Or use redis/memcached for distributed cache with TTL
```

---

### Phase 4: Specific Component Analysis

#### 4.1 Model/Tensor Memory Leaks

For ML models and tensor operations:

```bash
# Check GPU memory (if using GPU)
kubectl exec -it <pod-name> -n production -- nvidia-smi

# Check model memory usage
kubectl exec -it <pod-name> -n production -- python -c "
import torch
print('GPU memory allocated:', torch.cuda.memory_allocated())
print('GPU memory cached:', torch.cuda.memory_reserved())
"

# Check for unreleased tensors
kubectl exec -it <pod-name> -n production -- python -c "
import gc
import torch

gc.collect()
torch.cuda.empty_cache()

# Check for lingering tensors
for obj in gc.get_objects():
    if torch.is_tensor(obj):
        print(type(obj), obj.size())
"
```

**Solution for tensor leaks**:

```python
# Bad: Tensors not released
def inference(input_data):
    model = load_model()  # Loaded every time!
    result = model(input_data)
    return result
    # Model stays in memory

# Good: Reuse model, clean up tensors
model = load_model()  # Load once

def inference(input_data):
    with torch.no_grad():
        result = model(input_data)
    # Explicitly clean up if needed
    if hasattr(result, 'cpu'):
        result = result.cpu()
    return result
```

#### 4.2 Embedding Cache Leaks

```bash
# Check embedding cache size
curl http://localhost:8000/metrics | grep embedding_cache

# Check Qdrant memory usage
curl http://localhost:6333/metrics | grep memory

# Check vector cache in application
kubectl logs <pod-name> -n production | grep -i "embedding\|vector\|cache"
```

#### 4.3 File Handle Leaks

```bash
# Check open file handles
kubectl exec -it <pod-name> -n production -- lsof -p <pid> | wc -l

# List open files
kubectl exec -it <pod-name> -n production -- lsof -p <pid>

# Check file descriptor limit
kubectl exec -it <pod-name> -n production -- ulimit -n
```

**Solution for file handle leaks**:

```python
# Bad: File not closed
def read_config():
    f = open('config.yaml', 'r')
    data = f.read()
    return data
    # File never closed!

# Good: Use context manager
def read_config():
    with open('config.yaml', 'r') as f:
        data = f.read()
    return data
    # File automatically closed
```

---

## Common Causes and Solutions

### 1. Unreleased Database Connections

**Symptoms**:
- Memory grows with request volume
- Database connection count increases
- "Too many connections" errors

**Diagnosis**:
```bash
docker exec postgres psql -U ai_user -d ai_platform -c "
  SELECT count(*), state FROM pg_stat_activity GROUP BY state;
"
```

**Solution**:
```python
# Use connection pooling and context managers
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

engine = create_engine('postgresql://...', pool_size=20, max_overflow=0)
Session = sessionmaker(bind=engine)

def get_user(user_id):
    session = Session()
    try:
        user = session.query(User).filter_by(id=user_id).first()
        return user
    finally:
        session.close()  # Always close!
```

---

### 2. Event Listener Accumulation

**Symptoms**:
- Memory grows slowly but steadily
- Many duplicate event handlers
- Performance degrades over time

**Diagnosis**:
```python
# Check number of listeners
import sys
print(sys.getrefcount(event_emitter))
```

**Solution**:
```python
# Bad: Listener added but never removed
def setup_handler():
    event_emitter.on('data', handle_data)
    # Handler accumulates on every setup call!

# Good: Remove listener when done
def setup_handler():
    def handle_data(data):
        # Process data
        pass
    
    event_emitter.on('data', handle_data)
    return lambda: event_emitter.off('data', handle_data)

# Call the returned cleanup function when done
cleanup = setup_handler()
# ... later ...
cleanup()
```

---

### 3. Circular References

**Symptoms**:
- Objects not garbage collected
- Memory never released even after references removed
- `gc.garbage` contains objects

**Diagnosis**:
```python
import gc
gc.collect()
print('Garbage:', gc.garbage)
```

**Solution**:
```python
# Bad: Circular reference
class Node:
    def __init__(self, data):
        self.data = data
        self.parent = None
        self.children = []
    
    def add_child(self, child):
        child.parent = self  # Circular reference!
        self.children.append(child)

# Good: Use weak references
import weakref

class Node:
    def __init__(self, data):
        self.data = data
        self._parent = None
        self.children = []
    
    @property
    def parent(self):
        return self._parent() if self._parent else None
    
    @parent.setter
    def parent(self, value):
        self._parent = weakref.ref(value) if value else None
    
    def add_child(self, child):
        child.parent = self
        self.children.append(child)
```

---

### 4. Large Object Caching

**Symptoms**:
- Memory grows with unique requests
- Cache never shrinks
- Old data never evicted

**Diagnosis**:
```bash
curl http://localhost:8000/admin/cache/stats | jq
```

**Solution**:
```python
# Bad: Unbounded cache
cache = {}

def get_embedding(text):
    if text not in cache:
        cache[text] = compute_embedding(text)
    return cache[text]

# Good: LRU cache with size limit
from functools import lru_cache
from cachetools import LRUCache

cache = LRUCache(maxsize=10000)

def get_embedding(text):
    if text not in cache:
        cache[text] = compute_embedding(text)
    return cache[text]

# Or use TTL cache
from cachetools import TTLCache
cache = TTLCache(maxsize=10000, ttl=3600)  # 1 hour TTL
```

---

### 5. Logging Buffer Accumulation

**Symptoms**:
- Memory grows even with low traffic
- Log handlers accumulate
- Old logs not flushed

**Diagnosis**:
```python
import logging
for handler in logging.root.handlers:
    print(f'Handler: {handler}, Buffer size: {len(handler.buffer) if hasattr(handler, "buffer") else "N/A"}')
```

**Solution**:
```python
# Configure log rotation and buffer size
import logging
from logging.handlers import RotatingFileHandler

handler = RotatingFileHandler(
    'app.log',
    maxBytes=10*1024*1024,  # 10MB
    backupCount=5
)
handler.setLevel(logging.INFO)

# Ensure handlers are not duplicated
logger = logging.getLogger()
logger.handlers.clear()
logger.addHandler(handler)
```

---

### 6. Thread/Coroutine Leaks

**Symptoms**:
- Thread/coroutine count increases
- Memory grows with thread count
- Threads never terminate

**Diagnosis**:
```bash
# Check thread count
kubectl exec -it <pod-name> -n production -- ps -T -p <pid> | wc -l

# Or in Python
kubectl exec -it <pod-name> -n production -- python -c "
import threading
print('Active threads:', threading.active_count())
for thread in threading.enumerate():
    print(f'  {thread.name}: {thread.is_alive()}')
"
```

**Solution**:
```python
# Bad: Thread not joined
import threading

def process_task():
    thread = threading.Thread(target=heavy_operation)
    thread.start()
    # Thread never joined!

# Good: Use thread pool or join threads
from concurrent.futures import ThreadPoolExecutor

executor = ThreadPoolExecutor(max_workers=10)

def process_task():
    future = executor.submit(heavy_operation)
    return future
    # Thread pool manages thread lifecycle
```

---

## Mitigation Strategies

### Immediate Actions (< 5 minutes)

1. **Restart Affected Pods**
   ```bash
   kubectl rollout restart deployment/api-server -n production
   ```

2. **Increase Memory Limit** (temporary)
   ```bash
   kubectl set resources deployment/api-server \
     --limits=memory=8Gi \
     --requests=memory=4Gi \
     -n production
   ```

3. **Enable Swap** (if available and safe)
   ```bash
   # Generally not recommended for production
   # Only as last resort
   ```

4. **Reduce Load** (temporary)
   ```bash
   # Rate limit aggressive clients
   # Reject non-critical requests
   # Scale down to fewer replicas but with more memory each
   ```

### Short-term Fixes (< 1 hour)

1. **Force Garbage Collection**
   ```bash
   curl -X POST http://localhost:8000/admin/gc/collect
   ```

2. **Clear Caches**
   ```bash
   curl -X POST http://localhost:8000/admin/cache/clear
   ```

3. **Close Idle Connections**
   ```bash
   curl -X POST http://localhost:8000/admin/connections/close-idle
   ```

4. **Restart Service with Memory Profiling**
   ```bash
   kubectl set env deployment/api-server ENABLE_MEMORY_PROFILING=true -n production
   ```

### Long-term Solutions

1. **Fix Identified Leaks** (code changes)
2. **Implement Proper Resource Management**
3. **Add Memory Monitoring and Alerts**
4. **Regular Pod Restarts** (as workaround until fixed)
   ```bash
   # CronJob to restart pods daily
   kubectl create cronjob restart-api-server \
     --schedule="0 3 * * *" \
     --image=bitnami/kubectl \
     -- kubectl rollout restart deployment/api-server -n production
   ```

---

## Prevention

### Code Review Checklist

- [ ] All resources use context managers (`with` statements)
- [ ] Database connections properly closed
- [ ] HTTP clients properly closed
- [ ] File handles properly closed
- [ ] Caches have size limits and eviction policies
- [ ] Event listeners properly removed when done
- [ ] Threads/coroutines properly terminated
- [ ] No circular references (or using weak references)
- [ ] Large objects released when no longer needed
- [ ] Tensors/models released after use (ML code)

### Monitoring and Alerting

```yaml
# Prometheus alert rules
- alert: MemoryLeakDetected
  expr: |
    (container_memory_usage_bytes{namespace="production"} / 
     container_spec_memory_limit_bytes{namespace="production"}) > 0.85
  for: 30m
  labels:
    severity: warning
  annotations:
    summary: "Possible memory leak in {{ $labels.pod }}"
    description: "Memory usage >85% for 30 minutes"

- alert: MemoryGrowthRateHigh
  expr: |
    rate(container_memory_usage_bytes{namespace="production"}[1h]) > 0.05
  for: 1h
  labels:
    severity: warning
  annotations:
    summary: "High memory growth rate in {{ $labels.pod }}"
    description: "Memory growing at {{ $value }}% per hour"

- alert: OOMKillDetected
  expr: |
    rate(container_oom_events_total{namespace="production"}[5m]) > 0
  for: 1m
  labels:
    severity: critical
  annotations:
    summary: "OOM kill detected in {{ $labels.pod }}"
    description: "Pod was killed due to OOM"
```

### Testing

```python
# Memory leak test
import tracemalloc
import gc

def test_no_memory_leak():
    tracemalloc.start()
    
    # Run operation multiple times
    for i in range(1000):
        result = process_request(test_data)
        del result
        
        if i % 100 == 0:
            gc.collect()
            current, peak = tracemalloc.get_traced_memory()
            print(f'Iteration {i}: Current={current/1024/1024:.2f}MB, Peak={peak/1024/1024:.2f}MB')
    
    # Memory should not grow significantly
    final_memory, _ = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    
    assert final_memory < initial_memory * 1.1, "Memory leak detected"
```

### Best Practices

1. **Always use context managers** for resources
2. **Set cache size limits**
3. **Implement TTLs** for cached data
4. **Close connections explicitly**
5. **Use connection pooling**
6. **Avoid global mutable state**
7. **Profile memory regularly**
8. **Test under load**
9. **Monitor memory trends**
10. **Restart pods periodically** (as defense-in-depth)

---

## Appendix: Useful Tools

### Memory Profiling Tools

- **memory_profiler**: Line-by-line memory profiling
- **tracemalloc**: Built-in Python memory tracking
- **guppy3/heapy**: Heap analysis
- **objgraph**: Object reference visualization
- **pympler**: Memory profiling utilities
- **py-spy**: Sampling profiler (includes memory)

### Installation

```bash
pip install memory-profiler guppy3 objgraph pympler py-spy
```

### Quick Memory Analysis Script

```python
#!/usr/bin/env python3
# memory_analysis.py

import gc
import sys
from collections import Counter

def analyze_memory():
    gc.collect()
    
    # Count objects by type
    types = Counter(type(obj).__name__ for obj in gc.get_objects())
    
    print("Top 20 object types by count:")
    for obj_type, count in types.most_common(20):
        print(f"  {obj_type}: {count}")
    
    # Check for garbage
    print(f"\nUncollectable garbage: {len(gc.garbage)}")
    
    # Memory by type (approximate)
    print("\nTop 20 types by estimated memory:")
    type_sizes = {}
    for obj in gc.get_objects():
        obj_type = type(obj).__name__
        try:
            size = sys.getsizeof(obj)
            type_sizes[obj_type] = type_sizes.get(obj_type, 0) + size
        except:
            pass
    
    sorted_sizes = sorted(type_sizes.items(), key=lambda x: x[1], reverse=True)
    for obj_type, size in sorted_sizes[:20]:
        print(f"  {obj_type}: {size/1024/1024:.2f} MB")

if __name__ == '__main__':
    analyze_memory()
```

---

**Version**: 1.0  
**Last Updated**: 2025-01-30  
**Next Review**: 2025-02-28  
**Owner**: SRE Team
