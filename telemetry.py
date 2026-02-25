#!/usr/bin/env python3
"""
OpenTelemetry Tracing Configuration for MCPJungle Gateway.

Provides distributed tracing for MCP operations.
"""

import logging
import os
from typing import Optional

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

logger = logging.getLogger(__name__)


class TelemetryConfig:
    """OpenTelemetry configuration."""
    
    def __init__(
        self,
        service_name: str = "mcpjungle-gateway",
        service_version: str = "1.0.0",
        otlp_endpoint: Optional[str] = None,
        jaeger_endpoint: Optional[str] = None,
        enable_console_export: bool = False
    ):
        self.service_name = service_name
        self.service_version = service_version
        self.otlp_endpoint = otlp_endpoint or os.getenv("OTLP_ENDPOINT")
        self.jaeger_endpoint = jaeger_endpoint or os.getenv("JAEGER_ENDPOINT")
        self.enable_console_export = enable_console_export
        self.tracer_provider: Optional[TracerProvider] = None
        self.tracer: Optional[trace.Tracer] = None
    
    def setup(self):
        """Initialize OpenTelemetry tracing."""
        logger.info("Setting up OpenTelemetry tracing...")
        
        # Create resource
        resource = Resource.create({
            SERVICE_NAME: self.service_name,
            SERVICE_VERSION: self.service_version
        })
        
        # Create tracer provider
        self.tracer_provider = TracerProvider(resource=resource)
        
        # Add exporters
        exporters_added = 0
        
        # OTLP exporter (for OpenTelemetry Collector, Honeycomb, etc.)
        if self.otlp_endpoint:
            try:
                otlp_exporter = OTLPSpanExporter(endpoint=self.otlp_endpoint)
                self.tracer_provider.add_span_processor(
                    BatchSpanProcessor(otlp_exporter)
                )
                logger.info(f"OTLP exporter configured: {self.otlp_endpoint}")
                exporters_added += 1
            except Exception as e:
                logger.error(f"Failed to configure OTLP exporter: {e}")
        
        # Jaeger exporter
        if self.jaeger_endpoint:
            try:
                jaeger_exporter = JaegerExporter(
                    agent_host_name=self.jaeger_endpoint.split(":")[0],
                    agent_port=int(self.jaeger_endpoint.split(":")[1]) if ":" in self.jaeger_endpoint else 6831,
                )
                self.tracer_provider.add_span_processor(
                    BatchSpanProcessor(jaeger_exporter)
                )
                logger.info(f"Jaeger exporter configured: {self.jaeger_endpoint}")
                exporters_added += 1
            except Exception as e:
                logger.error(f"Failed to configure Jaeger exporter: {e}")
        
        # Console exporter (for debugging)
        if self.enable_console_export:
            from opentelemetry.sdk.trace.export import ConsoleSpanExporter
            console_exporter = ConsoleSpanExporter()
            self.tracer_provider.add_span_processor(
                BatchSpanProcessor(console_exporter)
            )
            logger.info("Console exporter configured")
            exporters_added += 1
        
        if exporters_added == 0:
            logger.warning("No trace exporters configured. Traces will not be exported.")
        
        # Set global tracer provider
        trace.set_tracer_provider(self.tracer_provider)
        
        # Get tracer
        self.tracer = trace.get_tracer(self.service_name, self.service_version)
        
        # Instrument FastAPI
        FastAPIInstrumentor.instrument()
        logger.info("FastAPI instrumented for tracing")
        
        # Instrument HTTPX
        HTTPXClientInstrumentor().instrument()
        logger.info("HTTPX instrumented for tracing")
        
        logger.info(
            f"OpenTelemetry tracing initialized "
            f"(service: {self.service_name}, exporters: {exporters_added})"
        )
    
    def get_tracer(self) -> trace.Tracer:
        """Get the configured tracer."""
        if not self.tracer:
            raise RuntimeError("Telemetry not initialized. Call setup() first.")
        return self.tracer
    
    def shutdown(self):
        """Shutdown tracer provider and flush remaining spans."""
        if self.tracer_provider:
            logger.info("Shutting down telemetry...")
            self.tracer_provider.shutdown()


# Global telemetry instance
_telemetry_config: Optional[TelemetryConfig] = None


def init_telemetry(
    service_name: str = "mcpjungle-gateway",
    service_version: str = "1.0.0",
    otlp_endpoint: Optional[str] = None,
    jaeger_endpoint: Optional[str] = None,
    enable_console_export: bool = False
) -> TelemetryConfig:
    """Initialize global telemetry configuration."""
    global _telemetry_config
    
    _telemetry_config = TelemetryConfig(
        service_name=service_name,
        service_version=service_version,
        otlp_endpoint=otlp_endpoint,
        jaeger_endpoint=jaeger_endpoint,
        enable_console_export=enable_console_export
    )
    
    _telemetry_config.setup()
    
    return _telemetry_config


def get_tracer() -> trace.Tracer:
    """Get the global tracer instance."""
    if not _telemetry_config:
        raise RuntimeError("Telemetry not initialized. Call init_telemetry() first.")
    return _telemetry_config.get_tracer()


def shutdown_telemetry():
    """Shutdown global telemetry."""
    if _telemetry_config:
        _telemetry_config.shutdown()
