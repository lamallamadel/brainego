#!/usr/bin/env python3
"""
Structured JSON logger for AI Platform services.

Provides JSON-formatted logging with trace context for Loki ingestion.
"""

import json
import logging
import sys
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from contextvars import ContextVar

# Context variables for trace context
trace_id_var: ContextVar[Optional[str]] = ContextVar('trace_id', default=None)
span_id_var: ContextVar[Optional[str]] = ContextVar('span_id', default=None)


class StructuredJSONFormatter(logging.Formatter):
    """
    JSON formatter for structured logging.
    
    Outputs logs in JSON format with:
    - timestamp (ISO8601)
    - level
    - logger name
    - message
    - trace_id (from context)
    - span_id (from context)
    - additional fields
    """
    
    def __init__(
        self,
        service_name: str,
        include_trace: bool = True,
        **kwargs
    ):
        """
        Initialize JSON formatter.
        
        Args:
            service_name: Name of the service
            include_trace: Include trace context if available
        """
        super().__init__()
        self.service_name = service_name
        self.include_trace = include_trace
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'service': self.service_name
        }
        
        # Add trace context if available
        if self.include_trace:
            trace_id = trace_id_var.get()
            span_id = span_id_var.get()
            
            if trace_id:
                log_data['trace_id'] = trace_id
            if span_id:
                log_data['span_id'] = span_id
        
        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        # Add extra fields from record
        if hasattr(record, 'extra_fields'):
            log_data.update(record.extra_fields)
        
        # Add specific fields for different log types
        if hasattr(record, 'user_id'):
            log_data['user_id'] = record.user_id
        if hasattr(record, 'session_id'):
            log_data['session_id'] = record.session_id
        if hasattr(record, 'request_id'):
            log_data['request_id'] = record.request_id
        if hasattr(record, 'duration_ms'):
            log_data['duration_ms'] = record.duration_ms
        if hasattr(record, 'status_code'):
            log_data['status_code'] = record.status_code
        if hasattr(record, 'endpoint'):
            log_data['endpoint'] = record.endpoint
        if hasattr(record, 'method'):
            log_data['method'] = record.method
        
        # MCP-specific fields
        if hasattr(record, 'mcp_server'):
            log_data['mcp_server'] = record.mcp_server
        if hasattr(record, 'mcp_operation'):
            log_data['mcp_operation'] = record.mcp_operation
        
        # MAX Serve-specific fields
        if hasattr(record, 'model'):
            log_data['model'] = record.model
        if hasattr(record, 'batch_size'):
            log_data['batch_size'] = record.batch_size
        if hasattr(record, 'latency_ms'):
            log_data['latency_ms'] = record.latency_ms
        
        # Learning Engine-specific fields
        if hasattr(record, 'task_id'):
            log_data['task_id'] = record.task_id
        if hasattr(record, 'epoch'):
            log_data['epoch'] = record.epoch
        if hasattr(record, 'loss'):
            log_data['loss'] = record.loss
        
        # Drift Monitor-specific fields
        if hasattr(record, 'drift_score'):
            log_data['drift_score'] = record.drift_score
        if hasattr(record, 'threshold'):
            log_data['threshold'] = record.threshold
        
        # Data Collection-specific fields
        if hasattr(record, 'source'):
            log_data['source'] = record.source
        
        # Memory-specific fields
        if hasattr(record, 'operation'):
            log_data['operation'] = record.operation
        
        return json.dumps(log_data)


def setup_structured_logging(
    service_name: str,
    level: int = logging.INFO,
    include_trace: bool = True
) -> logging.Logger:
    """
    Set up structured JSON logging for a service.
    
    Args:
        service_name: Name of the service
        level: Logging level
        include_trace: Include trace context in logs
        
    Returns:
        Configured logger
    """
    # Create root logger
    logger = logging.getLogger()
    logger.setLevel(level)
    
    # Remove existing handlers
    logger.handlers.clear()
    
    # Create console handler with JSON formatter
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    
    # Set JSON formatter
    formatter = StructuredJSONFormatter(
        service_name=service_name,
        include_trace=include_trace
    )
    handler.setFormatter(formatter)
    
    # Add handler to logger
    logger.addHandler(handler)
    
    return logger


def set_trace_context(trace_id: Optional[str], span_id: Optional[str] = None):
    """
    Set trace context for current execution context.
    
    Args:
        trace_id: Trace ID from OpenTelemetry
        span_id: Span ID from OpenTelemetry
    """
    trace_id_var.set(trace_id)
    if span_id:
        span_id_var.set(span_id)


def clear_trace_context():
    """Clear trace context."""
    trace_id_var.set(None)
    span_id_var.set(None)


def get_trace_context() -> Dict[str, Optional[str]]:
    """
    Get current trace context.
    
    Returns:
        Dictionary with trace_id and span_id
    """
    return {
        'trace_id': trace_id_var.get(),
        'span_id': span_id_var.get()
    }


class StructuredLogger:
    """
    Wrapper around Python logger with structured logging helpers.
    """
    
    def __init__(self, name: str):
        """
        Initialize structured logger.
        
        Args:
            name: Logger name
        """
        self.logger = logging.getLogger(name)
    
    def info(self, message: str, **kwargs):
        """Log info message with extra fields."""
        extra = {'extra_fields': kwargs}
        self.logger.info(message, extra=extra)
    
    def warning(self, message: str, **kwargs):
        """Log warning message with extra fields."""
        extra = {'extra_fields': kwargs}
        self.logger.warning(message, extra=extra)
    
    def error(self, message: str, **kwargs):
        """Log error message with extra fields."""
        extra = {'extra_fields': kwargs}
        self.logger.error(message, extra=extra)
    
    def debug(self, message: str, **kwargs):
        """Log debug message with extra fields."""
        extra = {'extra_fields': kwargs}
        self.logger.debug(message, extra=extra)
    
    def log_request(
        self,
        method: str,
        endpoint: str,
        status_code: int,
        duration_ms: float,
        **kwargs
    ):
        """
        Log HTTP request.
        
        Args:
            method: HTTP method
            endpoint: Request endpoint
            status_code: Response status code
            duration_ms: Request duration in milliseconds
        """
        message = f"{method} {endpoint} {status_code} {duration_ms:.2f}ms"
        extra = {
            'method': method,
            'endpoint': endpoint,
            'status_code': status_code,
            'duration_ms': duration_ms
        }
        extra.update(kwargs)
        self.logger.info(message, extra=extra)
    
    def log_inference(
        self,
        model: str,
        latency_ms: float,
        batch_size: int = 1,
        **kwargs
    ):
        """
        Log inference request.
        
        Args:
            model: Model name
            latency_ms: Inference latency in milliseconds
            batch_size: Batch size
        """
        message = f"Inference {model} {latency_ms:.2f}ms batch={batch_size}"
        extra = {
            'model': model,
            'latency_ms': latency_ms,
            'batch_size': batch_size
        }
        extra.update(kwargs)
        self.logger.info(message, extra=extra)
    
    def log_mcp_operation(
        self,
        server: str,
        operation: str,
        duration_ms: float,
        status: str = "success",
        **kwargs
    ):
        """
        Log MCP operation.
        
        Args:
            server: MCP server name
            operation: Operation name
            duration_ms: Operation duration in milliseconds
            status: Operation status
        """
        message = f"MCP {server}.{operation} {status} {duration_ms:.2f}ms"
        extra = {
            'mcp_server': server,
            'mcp_operation': operation,
            'duration_ms': duration_ms,
            'status': status
        }
        extra.update(kwargs)
        self.logger.info(message, extra=extra)
    
    def log_drift(
        self,
        model: str,
        drift_score: float,
        threshold: float,
        **kwargs
    ):
        """
        Log drift detection.
        
        Args:
            model: Model name
            drift_score: Drift score
            threshold: Drift threshold
        """
        message = f"Drift {model} score={drift_score:.4f} threshold={threshold:.4f}"
        extra = {
            'model': model,
            'drift_score': drift_score,
            'threshold': threshold
        }
        extra.update(kwargs)
        
        if drift_score > threshold:
            self.logger.warning(message, extra=extra)
        else:
            self.logger.info(message, extra=extra)


def get_structured_logger(name: str) -> StructuredLogger:
    """
    Get a structured logger instance.
    
    Args:
        name: Logger name
        
    Returns:
        StructuredLogger instance
    """
    return StructuredLogger(name)
