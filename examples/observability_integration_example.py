#!/usr/bin/env python3
"""
Example: Integrating Observability Stack into Services

Shows how to use metrics, structured logging, and tracing together.
"""

import time
import logging
from typing import Optional
from contextlib import contextmanager

from fastapi import FastAPI, Request
from fastapi.responses import Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from metrics_exporter import get_metrics_exporter
from structured_logger import setup_structured_logging, get_structured_logger, set_trace_context

# Initialize observability
setup_structured_logging('example-service', level=logging.INFO)
metrics = get_metrics_exporter('example-service')
logger = get_structured_logger(__name__)

# Create FastAPI app
app = FastAPI(title="Example Service with Observability")


@contextmanager
def observe_request(method: str, endpoint: str):
    """Context manager for observing requests."""
    start_time = time.time()
    status_code = 200
    
    try:
        yield
    except Exception as e:
        status_code = 500
        logger.error(f"Request failed: {e}", endpoint=endpoint, method=method)
        raise
    finally:
        duration = time.time() - start_time
        
        # Record metrics
        metrics.record_http_request(method, endpoint, status_code, duration)
        
        # Log request
        logger.log_request(
            method=method,
            endpoint=endpoint,
            status_code=status_code,
            duration_ms=duration * 1000
        )


@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    """
    Middleware for automatic observability.
    
    Extracts trace context and records metrics for all requests.
    """
    # Extract trace context from headers (if using OpenTelemetry)
    trace_id = request.headers.get('x-trace-id')
    span_id = request.headers.get('x-span-id')
    
    if trace_id:
        set_trace_context(trace_id, span_id)
    
    # Record request
    start_time = time.time()
    
    try:
        response = await call_next(request)
        duration = time.time() - start_time
        
        # Record metrics
        metrics.record_http_request(
            method=request.method,
            endpoint=request.url.path,
            status=response.status_code,
            duration=duration
        )
        
        # Log request
        logger.log_request(
            method=request.method,
            endpoint=request.url.path,
            status_code=response.status_code,
            duration_ms=duration * 1000,
            user_id=request.headers.get('x-user-id')
        )
        
        return response
    
    except Exception as e:
        duration = time.time() - start_time
        
        # Record error
        metrics.record_http_request(
            method=request.method,
            endpoint=request.url.path,
            status=500,
            duration=duration
        )
        
        logger.error(
            f"Request failed: {e}",
            method=request.method,
            endpoint=request.url.path,
            duration_ms=duration * 1000
        )
        
        raise


@app.get("/metrics")
async def metrics_endpoint():
    """Prometheus metrics endpoint."""
    return Response(
        content=metrics.get_metrics(),
        media_type=CONTENT_TYPE_LATEST
    )


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.post("/api/inference")
async def inference_endpoint(request: Request):
    """
    Example inference endpoint with full observability.
    """
    data = await request.json()
    model = data.get('model', 'llama-3.3-8b')
    
    # Simulate inference
    start_time = time.time()
    
    try:
        # Simulate work
        time.sleep(0.25)
        
        duration = time.time() - start_time
        
        # Record inference metrics
        metrics.record_inference(
            model=model,
            status='success',
            duration=duration,
            prompt_tokens=100,
            completion_tokens=50,
            batch_size=1
        )
        
        # Log inference
        logger.log_inference(
            model=model,
            latency_ms=duration * 1000,
            batch_size=1,
            user_id=request.headers.get('x-user-id')
        )
        
        return {
            'status': 'success',
            'model': model,
            'latency_ms': duration * 1000
        }
    
    except Exception as e:
        duration = time.time() - start_time
        
        # Record error
        metrics.record_inference(
            model=model,
            status='error',
            duration=duration
        )
        
        logger.error(f"Inference failed: {e}", model=model)
        
        raise


@app.post("/api/mcp/execute")
async def mcp_endpoint(request: Request):
    """
    Example MCP endpoint with observability.
    """
    data = await request.json()
    server = data.get('server', 'github')
    operation = data.get('operation', 'search')
    
    start_time = time.time()
    
    try:
        # Simulate MCP operation
        time.sleep(0.05)
        
        duration = time.time() - start_time
        
        # Record MCP metrics
        metrics.record_mcp_operation(
            server=server,
            operation=operation,
            status='success',
            duration=duration
        )
        
        # Log MCP operation
        logger.log_mcp_operation(
            server=server,
            operation=operation,
            duration_ms=duration * 1000,
            status='success'
        )
        
        return {
            'status': 'success',
            'server': server,
            'operation': operation
        }
    
    except Exception as e:
        duration = time.time() - start_time
        
        # Record error
        metrics.record_mcp_operation(
            server=server,
            operation=operation,
            status='error',
            duration=duration
        )
        
        logger.error(f"MCP operation failed: {e}", 
                    mcp_server=server, 
                    mcp_operation=operation)
        
        raise


@app.post("/api/memory/search")
async def memory_endpoint(request: Request):
    """
    Example memory endpoint with observability.
    """
    data = await request.json()
    user_id = data.get('user_id', 'user123')
    query = data.get('query', '')
    
    start_time = time.time()
    
    try:
        # Simulate memory search
        time.sleep(0.1)
        results_count = 5
        
        duration = time.time() - start_time
        
        # Record memory metrics
        metrics.record_memory_operation(
            operation='search',
            status='success',
            duration=duration,
            user_id=user_id,
            results_count=results_count
        )
        
        # Update memory stats
        metrics.update_memory_stats(user_id, 42)
        
        # Log with structured fields
        logger.info(
            f"Memory search completed: {results_count} results",
            user_id=user_id,
            operation='search',
            duration_ms=duration * 1000,
            results_count=results_count
        )
        
        return {
            'status': 'success',
            'results_count': results_count,
            'user_id': user_id
        }
    
    except Exception as e:
        duration = time.time() - start_time
        
        # Record error
        metrics.record_memory_operation(
            operation='search',
            status='error',
            duration=duration,
            user_id=user_id
        )
        
        logger.error(f"Memory search failed: {e}", 
                    user_id=user_id, 
                    operation='search')
        
        raise


@app.post("/api/drift/check")
async def drift_endpoint(request: Request):
    """
    Example drift check endpoint with observability.
    """
    data = await request.json()
    model = data.get('model', 'llama-3.3-8b')
    
    start_time = time.time()
    
    try:
        # Simulate drift detection
        time.sleep(5.0)
        drift_score = 0.12
        threshold = 0.15
        status = 'normal' if drift_score < threshold else 'warning'
        
        duration = time.time() - start_time
        
        # Update drift metrics
        metrics.update_drift_score(
            model=model,
            score=drift_score,
            status=status,
            duration=duration
        )
        
        # Log drift check
        logger.log_drift(
            model=model,
            drift_score=drift_score,
            threshold=threshold,
            status=status
        )
        
        return {
            'status': status,
            'drift_score': drift_score,
            'threshold': threshold,
            'model': model
        }
    
    except Exception as e:
        logger.error(f"Drift check failed: {e}", model=model)
        raise


@app.post("/api/budget/update")
async def budget_endpoint(request: Request):
    """
    Example budget update endpoint with observability.
    """
    data = await request.json()
    session_id = data.get('session_id', 'session123')
    used_bytes = data.get('used_bytes', 750000)
    total_bytes = data.get('total_bytes', 1000000)
    
    # Update budget metrics
    metrics.update_budget(
        session_id=session_id,
        total_bytes=total_bytes,
        used_bytes=used_bytes
    )
    
    utilization = (used_bytes / total_bytes * 100) if total_bytes > 0 else 0
    
    # Log budget update
    logger.info(
        f"Budget updated: {utilization:.1f}% used",
        session_id=session_id,
        used_bytes=used_bytes,
        total_bytes=total_bytes,
        utilization=utilization
    )
    
    return {
        'status': 'success',
        'session_id': session_id,
        'utilization': utilization
    }


@app.get("/api/gpu/stats")
async def gpu_stats_endpoint():
    """
    Example GPU stats endpoint with observability.
    """
    # Simulate GPU stats
    gpu_id = '0'
    
    # Update GPU metrics
    metrics.update_gpu_stats(
        gpu_id=gpu_id,
        utilization=75.5,
        memory_used=8000000000,
        memory_total=16000000000,
        temperature=72.0
    )
    
    logger.info(
        "GPU stats updated",
        gpu_id=gpu_id,
        utilization=75.5,
        temperature=72.0
    )
    
    return {
        'gpu_id': gpu_id,
        'utilization': 75.5,
        'memory_used': 8000000000,
        'memory_total': 16000000000,
        'temperature': 72.0
    }


@app.post("/api/router/decide")
async def router_endpoint(request: Request):
    """
    Example router decision endpoint with observability.
    """
    data = await request.json()
    query = data.get('query', '')
    
    start_time = time.time()
    
    # Simulate routing decision
    model = 'llama-3.3-8b'
    reason = 'general_query'
    
    duration = time.time() - start_time
    
    # Record routing decision
    metrics.record_routing_decision(
        model=model,
        reason=reason,
        duration=duration
    )
    
    logger.info(
        f"Routing decision: {model} ({reason})",
        model=model,
        reason=reason,
        duration_ms=duration * 1000
    )
    
    return {
        'model': model,
        'reason': reason
    }


@app.post("/api/queue/update")
async def queue_endpoint(request: Request):
    """
    Example queue metrics endpoint.
    """
    data = await request.json()
    service = data.get('service', 'gateway')
    depth = data.get('depth', 10)
    wait_time = data.get('wait_time', 0.05)
    
    # Update queue metrics
    metrics.update_queue_depth(service, depth)
    metrics.record_queue_wait(service, wait_time)
    
    logger.info(
        f"Queue updated: depth={depth}, wait={wait_time}s",
        service=service,
        queue_depth=depth,
        wait_time=wait_time
    )
    
    return {
        'service': service,
        'depth': depth,
        'wait_time': wait_time
    }


@app.post("/api/cache/access")
async def cache_endpoint(request: Request):
    """
    Example cache access endpoint.
    """
    data = await request.json()
    cache_type = data.get('cache_type', 'redis')
    hit = data.get('hit', True)
    
    # Record cache access
    if hit:
        metrics.record_cache_hit(cache_type)
    else:
        metrics.record_cache_miss(cache_type)
    
    logger.info(
        f"Cache {'hit' if hit else 'miss'}: {cache_type}",
        cache_type=cache_type,
        cache_hit=hit
    )
    
    return {
        'cache_type': cache_type,
        'hit': hit
    }


if __name__ == '__main__':
    import uvicorn
    
    uvicorn.run(
        app,
        host='0.0.0.0',
        port=8888,
        log_config=None  # Disable default logging, use structured logging
    )
