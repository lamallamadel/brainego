#!/usr/bin/env python3
"""
Prometheus metrics exporter for AI Platform services.

Provides custom metrics for:
- MAX Serve inference
- MCPJungle operations
- Memory Engine operations
- Gateway routing
- Drift detection
- Budget tracking
"""

import logging
from typing import Optional, Dict, Any
from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    Summary,
    Info,
    generate_latest,
    REGISTRY,
    CollectorRegistry
)

logger = logging.getLogger(__name__)


class MetricsExporter:
    """Prometheus metrics exporter for AI Platform."""
    
    def __init__(self, service_name: str, registry: Optional[CollectorRegistry] = None):
        """
        Initialize metrics exporter.
        
        Args:
            service_name: Name of the service (e.g., 'gateway', 'max-serve')
            registry: Prometheus registry (uses default if None)
        """
        self.service_name = service_name
        self.registry = registry or REGISTRY
        
        # HTTP request metrics
        self.http_requests_total = Counter(
            'http_requests_total',
            'Total HTTP requests',
            ['method', 'endpoint', 'status'],
            registry=self.registry
        )
        
        self.http_request_duration_seconds = Histogram(
            'http_request_duration_seconds',
            'HTTP request latency',
            ['method', 'endpoint'],
            buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
            registry=self.registry
        )
        
        # Inference metrics (MAX Serve)
        self.inference_requests_total = Counter(
            'inference_requests_total',
            'Total inference requests',
            ['model', 'status'],
            registry=self.registry
        )
        
        self.inference_duration_seconds = Histogram(
            'inference_duration_seconds',
            'Inference latency',
            ['model'],
            buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
            registry=self.registry
        )
        
        self.inference_tokens_total = Counter(
            'inference_tokens_total',
            'Total tokens processed',
            ['model', 'type'],  # type: prompt or completion
            registry=self.registry
        )
        
        self.inference_batch_size = Histogram(
            'inference_batch_size',
            'Inference batch size',
            ['model'],
            buckets=[1, 2, 4, 8, 16, 32, 64],
            registry=self.registry
        )
        
        # MCP metrics
        self.mcp_requests_total = Counter(
            'mcp_requests_total',
            'Total MCP requests',
            ['server', 'operation', 'status'],
            registry=self.registry
        )
        
        self.mcp_operation_duration_seconds = Histogram(
            'mcp_operation_duration_seconds',
            'MCP operation latency',
            ['server', 'operation'],
            buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0],
            registry=self.registry
        )
        
        # Memory Engine metrics
        self.memory_operations_total = Counter(
            'memory_operations_total',
            'Total memory operations',
            ['operation', 'status'],  # operation: add, search, update
            registry=self.registry
        )
        
        self.memory_operation_duration_seconds = Histogram(
            'memory_operation_duration_seconds',
            'Memory operation latency',
            ['operation'],
            buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0],
            registry=self.registry
        )
        
        self.memory_items_total = Gauge(
            'memory_items_total',
            'Total items in memory',
            ['user_id'],
            registry=self.registry
        )
        
        self.memory_search_results = Histogram(
            'memory_search_results',
            'Number of memory search results',
            buckets=[0, 1, 5, 10, 20, 50, 100],
            registry=self.registry
        )
        
        # Budget metrics
        self.memory_budget_total_bytes = Gauge(
            'memory_budget_total_bytes',
            'Total memory budget in bytes',
            ['session_id'],
            registry=self.registry
        )
        
        self.memory_budget_used_bytes = Gauge(
            'memory_budget_used_bytes',
            'Used memory budget in bytes',
            ['session_id'],
            registry=self.registry
        )
        
        self.memory_budget_utilization = Gauge(
            'memory_budget_utilization',
            'Memory budget utilization percentage',
            ['session_id'],
            registry=self.registry
        )
        
        # Drift metrics
        self.drift_score = Gauge(
            'drift_score',
            'Current drift score',
            ['model'],
            registry=self.registry
        )
        
        self.drift_checks_total = Counter(
            'drift_checks_total',
            'Total drift checks',
            ['model', 'status'],  # status: normal, warning, critical
            registry=self.registry
        )
        
        self.drift_detection_duration_seconds = Histogram(
            'drift_detection_duration_seconds',
            'Drift detection latency',
            buckets=[1.0, 5.0, 10.0, 30.0, 60.0],
            registry=self.registry
        )
        
        # GPU metrics
        self.gpu_utilization = Gauge(
            'gpu_utilization_percent',
            'GPU utilization percentage',
            ['gpu_id'],
            registry=self.registry
        )
        
        self.gpu_memory_used_bytes = Gauge(
            'gpu_memory_used_bytes',
            'GPU memory used in bytes',
            ['gpu_id'],
            registry=self.registry
        )
        
        self.gpu_memory_total_bytes = Gauge(
            'gpu_memory_total_bytes',
            'GPU total memory in bytes',
            ['gpu_id'],
            registry=self.registry
        )
        
        self.gpu_temperature_celsius = Gauge(
            'gpu_temperature_celsius',
            'GPU temperature in Celsius',
            ['gpu_id'],
            registry=self.registry
        )
        
        # Router metrics
        self.router_decisions_total = Counter(
            'router_decisions_total',
            'Total routing decisions',
            ['model', 'reason'],
            registry=self.registry
        )
        
        self.router_decision_duration_seconds = Histogram(
            'router_decision_duration_seconds',
            'Router decision latency',
            buckets=[0.001, 0.005, 0.01, 0.05, 0.1],
            registry=self.registry
        )
        
        # Queue metrics
        self.request_queue_depth = Gauge(
            'request_queue_depth',
            'Current request queue depth',
            ['service'],
            registry=self.registry
        )
        
        self.request_queue_wait_seconds = Histogram(
            'request_queue_wait_seconds',
            'Request queue wait time',
            ['service'],
            buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0],
            registry=self.registry
        )
        
        # Cache metrics
        self.cache_hits_total = Counter(
            'cache_hits_total',
            'Total cache hits',
            ['cache_type'],
            registry=self.registry
        )
        
        self.cache_misses_total = Counter(
            'cache_misses_total',
            'Total cache misses',
            ['cache_type'],
            registry=self.registry
        )
        
        # Service info
        self.service_info = Info(
            'service',
            'Service information',
            registry=self.registry
        )
        
        self.service_info.info({
            'name': service_name,
            'version': '1.0.0'
        })
        
        logger.info(f"Metrics exporter initialized for {service_name}")
    
    def record_http_request(
        self,
        method: str,
        endpoint: str,
        status: int,
        duration: float
    ):
        """Record HTTP request metrics."""
        self.http_requests_total.labels(
            method=method,
            endpoint=endpoint,
            status=status
        ).inc()
        
        self.http_request_duration_seconds.labels(
            method=method,
            endpoint=endpoint
        ).observe(duration)
    
    def record_inference(
        self,
        model: str,
        status: str,
        duration: float,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        batch_size: int = 1
    ):
        """Record inference metrics."""
        self.inference_requests_total.labels(
            model=model,
            status=status
        ).inc()
        
        self.inference_duration_seconds.labels(
            model=model
        ).observe(duration)
        
        if prompt_tokens > 0:
            self.inference_tokens_total.labels(
                model=model,
                type='prompt'
            ).inc(prompt_tokens)
        
        if completion_tokens > 0:
            self.inference_tokens_total.labels(
                model=model,
                type='completion'
            ).inc(completion_tokens)
        
        self.inference_batch_size.labels(
            model=model
        ).observe(batch_size)
    
    def record_mcp_operation(
        self,
        server: str,
        operation: str,
        status: str,
        duration: float
    ):
        """Record MCP operation metrics."""
        self.mcp_requests_total.labels(
            server=server,
            operation=operation,
            status=status
        ).inc()
        
        self.mcp_operation_duration_seconds.labels(
            server=server,
            operation=operation
        ).observe(duration)
    
    def record_memory_operation(
        self,
        operation: str,
        status: str,
        duration: float,
        user_id: Optional[str] = None,
        results_count: Optional[int] = None
    ):
        """Record memory operation metrics."""
        self.memory_operations_total.labels(
            operation=operation,
            status=status
        ).inc()
        
        self.memory_operation_duration_seconds.labels(
            operation=operation
        ).observe(duration)
        
        if results_count is not None:
            self.memory_search_results.observe(results_count)
    
    def update_memory_stats(self, user_id: str, item_count: int):
        """Update memory statistics."""
        self.memory_items_total.labels(user_id=user_id).set(item_count)
    
    def update_budget(
        self,
        session_id: str,
        total_bytes: int,
        used_bytes: int
    ):
        """Update budget metrics."""
        self.memory_budget_total_bytes.labels(
            session_id=session_id
        ).set(total_bytes)
        
        self.memory_budget_used_bytes.labels(
            session_id=session_id
        ).set(used_bytes)
        
        utilization = (used_bytes / total_bytes * 100) if total_bytes > 0 else 0
        self.memory_budget_utilization.labels(
            session_id=session_id
        ).set(utilization)
    
    def update_drift_score(
        self,
        model: str,
        score: float,
        status: str,
        duration: float
    ):
        """Update drift metrics."""
        self.drift_score.labels(model=model).set(score)
        
        self.drift_checks_total.labels(
            model=model,
            status=status
        ).inc()
        
        self.drift_detection_duration_seconds.observe(duration)
    
    def update_gpu_stats(
        self,
        gpu_id: str,
        utilization: float,
        memory_used: int,
        memory_total: int,
        temperature: float
    ):
        """Update GPU metrics."""
        self.gpu_utilization.labels(gpu_id=gpu_id).set(utilization)
        self.gpu_memory_used_bytes.labels(gpu_id=gpu_id).set(memory_used)
        self.gpu_memory_total_bytes.labels(gpu_id=gpu_id).set(memory_total)
        self.gpu_temperature_celsius.labels(gpu_id=gpu_id).set(temperature)
    
    def record_routing_decision(
        self,
        model: str,
        reason: str,
        duration: float
    ):
        """Record routing decision metrics."""
        self.router_decisions_total.labels(
            model=model,
            reason=reason
        ).inc()
        
        self.router_decision_duration_seconds.observe(duration)
    
    def update_queue_depth(self, service: str, depth: int):
        """Update queue depth metric."""
        self.request_queue_depth.labels(service=service).set(depth)
    
    def record_queue_wait(self, service: str, wait_time: float):
        """Record queue wait time."""
        self.request_queue_wait_seconds.labels(
            service=service
        ).observe(wait_time)
    
    def record_cache_hit(self, cache_type: str):
        """Record cache hit."""
        self.cache_hits_total.labels(cache_type=cache_type).inc()
    
    def record_cache_miss(self, cache_type: str):
        """Record cache miss."""
        self.cache_misses_total.labels(cache_type=cache_type).inc()
    
    def get_metrics(self) -> bytes:
        """Get current metrics in Prometheus format."""
        return generate_latest(self.registry)


# Global metrics exporters
_metrics_exporters: Dict[str, MetricsExporter] = {}


def get_metrics_exporter(service_name: str) -> MetricsExporter:
    """
    Get or create metrics exporter for a service.
    
    Args:
        service_name: Name of the service
        
    Returns:
        MetricsExporter instance
    """
    if service_name not in _metrics_exporters:
        _metrics_exporters[service_name] = MetricsExporter(service_name)
    
    return _metrics_exporters[service_name]
