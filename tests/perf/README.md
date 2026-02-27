# Performance Benchmarks

This folder contains repeatable performance baselines for the API.

## `/v1/chat` end-to-end baseline (AFR-30)

Run the benchmark against a running API server:

```bash
python tests/perf/benchmark_v1_chat_latency.py \
  --base-url http://localhost:8000 \
  --iterations 20 \
  --concurrency 4
```

Artifacts are written to:

- `tests/perf/artifacts/v1_chat_benchmark_report.json`
- `tests/perf/artifacts/v1_chat_benchmark_report.md`

### What it measures

- End-to-end latency for typical `/v1/chat` prompt shapes
- Throughput (requests/second)
- Success rate
- Latency percentiles (p50/p95/p99)

### Included scenarios

1. `standard_rag_query` (goal: p95 latency < 3000 ms)
2. `memory_follow_up`
3. `chat_without_rag`

### Notes

- Run at least 3 times and keep the median p95 as baseline.
- Benchmark should run in a stable environment (no concurrent heavy jobs).
- If success rate drops, fix reliability first before comparing latency numbers.
