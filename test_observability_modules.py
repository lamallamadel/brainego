#!/usr/bin/env python3
"""
Test observability modules (metrics_exporter and structured_logger).
"""

import sys
import logging

def test_metrics_exporter():
    """Test metrics_exporter module."""
    print("Testing metrics_exporter module...")
    
    try:
        from metrics_exporter import get_metrics_exporter, MetricsExporter
        
        # Create exporter
        metrics = get_metrics_exporter('test-service')
        
        # Test HTTP metrics
        metrics.record_http_request('GET', '/test', 200, 0.1)
        
        # Test inference metrics
        metrics.record_inference('test-model', 'success', 0.5, 100, 50, 1)
        
        # Test MCP metrics
        metrics.record_mcp_operation('test-server', 'test-op', 'success', 0.05)
        
        # Test memory metrics
        metrics.record_memory_operation('search', 'success', 0.1, 'user123', 5)
        
        # Test budget metrics
        metrics.update_budget('session123', 1000, 750)
        
        # Test drift metrics
        metrics.update_drift_score('test-model', 0.12, 'normal', 5.0)
        
        # Test GPU metrics
        metrics.update_gpu_stats('0', 75.0, 8000000000, 16000000000, 70.0)
        
        # Test routing metrics
        metrics.record_routing_decision('test-model', 'test-reason', 0.01)
        
        # Test queue metrics
        metrics.update_queue_depth('test-service', 10)
        metrics.record_queue_wait('test-service', 0.05)
        
        # Test cache metrics
        metrics.record_cache_hit('test-cache')
        metrics.record_cache_miss('test-cache')
        
        # Get metrics output
        output = metrics.get_metrics()
        assert len(output) > 0, "Metrics output should not be empty"
        
        print("✓ metrics_exporter tests passed")
        return True
    
    except Exception as e:
        print(f"✗ metrics_exporter tests failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_structured_logger():
    """Test structured_logger module."""
    print("Testing structured_logger module...")
    
    try:
        from structured_logger import (
            setup_structured_logging,
            get_structured_logger,
            set_trace_context,
            clear_trace_context,
            get_trace_context,
            StructuredJSONFormatter
        )
        
        # Setup logging
        setup_structured_logging('test-service', level=logging.INFO)
        
        # Get logger
        logger = get_structured_logger('test')
        
        # Test basic logging
        logger.info("Test message", test_field="test_value")
        logger.warning("Test warning")
        logger.error("Test error")
        logger.debug("Test debug")
        
        # Test trace context
        set_trace_context('trace123', 'span456')
        context = get_trace_context()
        assert context['trace_id'] == 'trace123', "Trace ID should match"
        assert context['span_id'] == 'span456', "Span ID should match"
        
        # Test specialized logging
        logger.log_request('POST', '/test', 200, 123.5)
        logger.log_inference('test-model', 250.0, batch_size=4)
        logger.log_mcp_operation('test-server', 'test-op', 50.0, status='success')
        logger.log_drift('test-model', 0.15, 0.10)
        
        # Clear trace context
        clear_trace_context()
        context = get_trace_context()
        assert context['trace_id'] is None, "Trace ID should be None after clear"
        
        print("✓ structured_logger tests passed")
        return True
    
    except Exception as e:
        print(f"✗ structured_logger tests failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("=" * 60)
    print("Testing Observability Modules")
    print("=" * 60)
    print()
    
    results = []
    
    # Test metrics_exporter
    results.append(test_metrics_exporter())
    print()
    
    # Test structured_logger
    results.append(test_structured_logger())
    print()
    
    # Summary
    print("=" * 60)
    if all(results):
        print("✓ All observability module tests passed")
        print("=" * 60)
        return 0
    else:
        print("✗ Some observability module tests failed")
        print("=" * 60)
        return 1


if __name__ == '__main__':
    sys.exit(main())
