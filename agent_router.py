#!/usr/bin/env python3
"""
Agent Router for multi-model deployment with intent classification.
Supports Llama 3.3 8B (general), Qwen 2.5 Coder 7B (code), DeepSeek R1 7B (reasoning).
"""

import os
import time
import logging
import asyncio
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass

import yaml
import httpx
from prometheus_client import Counter, Histogram, Gauge, start_http_server

from circuit_breaker import get_circuit_breaker, CircuitBreakerConfig, CircuitBreakerError

from intent_classifier import Intent, IntentClassifier

logger = logging.getLogger(__name__)


@dataclass
class ModelConfig:
    """Model configuration."""
    name: str
    endpoint: str
    description: str
    capabilities: List[str]
    max_tokens: int
    temperature: float
    aliases: List[str]
    health_status: bool = False
    consecutive_failures: int = 0
    consecutive_successes: int = 0


@dataclass
class RoutingConfig:
    """Routing configuration."""
    primary_model: Dict[str, str]
    fallback_chains: Dict[str, List[str]]
    timeouts: Dict[str, int]
    retry: Dict[str, Any]


class PrometheusMetrics:
    """Prometheus metrics for agent router."""
    
    def __init__(self):
        # Request counters
        self.requests_total = Counter(
            'agent_router_requests_total',
            'Total number of requests',
            ['model', 'intent', 'status']
        )
        
        self.model_requests = Counter(
            'agent_router_model_requests_total',
            'Total requests per model',
            ['model']
        )
        
        self.fallback_requests = Counter(
            'agent_router_fallback_requests_total',
            'Total fallback requests',
            ['from_model', 'to_model']
        )

        self.model_fallbacks = Counter(
            'agent_router_model_fallbacks_total',
            'Fallback attempts involving each model',
            ['model', 'role']
        )
        
        self.fallback_rate = Gauge(
            'agent_router_fallback_rate',
            'Current fallback rate',
            ['model']
        )
        
        # Latency histograms
        self.latency_seconds = Histogram(
            'agent_router_latency_seconds',
            'Request latency in seconds',
            ['model', 'intent'],
            buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0)
        )
        
        self.classification_latency = Histogram(
            'agent_router_classification_latency_seconds',
            'Intent classification latency in seconds',
            buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0)
        )
        
        # Intent counters
        self.intent_classification = Counter(
            'agent_router_intent_classification_total',
            'Intent classification counts',
            ['intent', 'confidence']
        )
        
        # Health status
        self.model_health = Gauge(
            'agent_router_model_health',
            'Model health status (1=healthy, 0=unhealthy)',
            ['model']
        )
        
        # Error counters
        self.errors_total = Counter(
            'agent_router_errors_total',
            'Total errors',
            ['model', 'error_type']
        )


class IntentClassifier:
    """Classify user intent based on message content."""
    
    def __init__(self, config: Dict[str, Any]):
        self.code_keywords = set(config['code_keywords'])
        self.reasoning_keywords = set(config['reasoning_keywords'])
        self.thresholds = config['thresholds']
        
        # Compile regex patterns for faster matching
        self.code_pattern = re.compile(
            r'\b(' + '|'.join(map(re.escape, self.code_keywords)) + r')\b',
            re.IGNORECASE
        )
        self.reasoning_pattern = re.compile(
            r'\b(' + '|'.join(map(re.escape, self.reasoning_keywords)) + r')\b',
            re.IGNORECASE
        )
    
    def classify(self, text: str) -> Tuple[Intent, float]:
        """
        Classify intent from text.
        
        Returns:
            Tuple of (intent, confidence_score)
        """
        text_lower = text.lower()
        
        # Count keyword matches
        code_matches = len(self.code_pattern.findall(text))
        reasoning_matches = len(self.reasoning_pattern.findall(text))

        # Lightweight structural heuristics
        if "```" in text:
            code_matches += 2
        if any(token in text_lower for token in ["step by step", "first," , "therefore", "hypothesis"]):
            reasoning_matches += 1

        # Calculate confidence scores
        total_words = len(text_lower.split())
        if total_words == 0:
            return Intent.GENERAL, 1.0

        normalizer = max(total_words * 0.1, 1)
        code_score = min(code_matches / normalizer, 1.0)
        reasoning_score = min(reasoning_matches / normalizer, 1.0)
        
        # Determine intent
        if code_score >= self.thresholds['medium'] and code_score >= reasoning_score:
            return Intent.CODE, code_score
        elif reasoning_score >= self.thresholds['medium']:
            return Intent.REASONING, reasoning_score
        else:
            # Default to general
            return Intent.GENERAL, 1.0 - max(code_score, reasoning_score)


class AgentRouter:
    """
    Agent router with intent classification and model selection.
    Supports dynamic routing, fallback chains, and Prometheus metrics.
    """
    
    def __init__(self, config_path: str = "configs/agent-router.yaml"):
        """Initialize agent router with configuration."""
        self.config_path = config_path
        self.models: Dict[str, ModelConfig] = {}
        self.routing_config: Optional[RoutingConfig] = None
        self.intent_classifier: Optional[IntentClassifier] = None
        self.metrics = PrometheusMetrics()
        self.health_check_enabled = False
        self.health_check_task = None
        self.circuit_breakers: Dict[str, Any] = {}
        self.model_aliases: Dict[str, str] = {}
        
        self._load_config()
        self._initialize_metrics()
        self._initialize_circuit_breakers()
    
    def _load_config(self):
        """Load configuration from YAML file."""
        logger.info(f"Loading configuration from {self.config_path}")
        
        with open(self.config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        # Load model configurations
        for model_id, model_cfg in config['models'].items():
            aliases = model_cfg.get('aliases', [])
            self.models[model_id] = ModelConfig(
                name=model_cfg['name'],
                endpoint=model_cfg['endpoint'],
                description=model_cfg['description'],
                capabilities=model_cfg['capabilities'],
                max_tokens=model_cfg['max_tokens'],
                temperature=model_cfg['temperature'],
                aliases=aliases
            )
            alias_keys = {
                model_id.lower(),
                model_cfg['name'].lower(),
                model_cfg['name'].replace('_', '-').lower(),
                *[alias.lower() for alias in aliases]
            }
            for alias_key in alias_keys:
                self.model_aliases[alias_key] = model_id
        
        # Load routing configuration
        routing = config['routing']
        self.routing_config = RoutingConfig(
            primary_model=routing['primary_model'],
            fallback_chains=routing['fallback_chains'],
            timeouts=routing['timeouts'],
            retry=routing['retry']
        )
        
        # Load intent classifier
        self.intent_classifier = IntentClassifier(config['intent_classifier'])
        
        # Load health check settings
        health_cfg = config.get('health_check', {})
        self.health_check_enabled = health_cfg.get('enabled', True)
        self.health_check_interval = health_cfg.get('interval_seconds', 30)
        self.unhealthy_threshold = health_cfg.get('unhealthy_threshold', 3)
        self.healthy_threshold = health_cfg.get('healthy_threshold', 2)
        
        # Load metrics settings
        metrics_cfg = config.get('metrics', {})
        if metrics_cfg.get('enabled', True):
            prometheus_port = metrics_cfg.get('prometheus_port', 8001)
            try:
                start_http_server(prometheus_port)
                logger.info(f"Prometheus metrics server started on port {prometheus_port}")
            except Exception as e:
                logger.warning(f"Failed to start Prometheus server: {e}")
        
        logger.info(f"Loaded configuration with {len(self.models)} models")
    
    def _initialize_metrics(self):
        """Initialize Prometheus metrics."""
        for model_id, model in self.models.items():
            self.metrics.model_health.labels(model=model_id).set(1 if model.health_status else 0)
            self.metrics.fallback_rate.labels(model=model_id).set(0)
    
    def _initialize_circuit_breakers(self):
        """Initialize circuit breakers for each model."""
        cb_config = CircuitBreakerConfig(
            failure_threshold=3,
            timeout_seconds=5.0,
            recovery_timeout_seconds=30.0,
            success_threshold=2
        )
        
        for model_id in self.models.keys():
            self.circuit_breakers[model_id] = get_circuit_breaker(
                f"model_{model_id}",
                cb_config
            )
        
        logger.info(f"Initialized circuit breakers for {len(self.circuit_breakers)} models")
    
    async def start_health_checks(self):
        """Start periodic health checks for all models."""
        if not self.health_check_enabled:
            return

        # Run an initial probe immediately so API readiness reflects real
        # model availability before the first interval elapses.
        await self._check_all_models_health()
        
        logger.info("Starting health check background task")
        self.health_check_task = asyncio.create_task(self._health_check_loop())
    
    async def stop_health_checks(self):
        """Stop health check background task."""
        if self.health_check_task:
            self.health_check_task.cancel()
            try:
                await self.health_check_task
            except asyncio.CancelledError:
                pass
    
    async def _health_check_loop(self):
        """Periodic health check loop."""
        while True:
            try:
                await asyncio.sleep(self.health_check_interval)
                await self._check_all_models_health()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in health check loop: {e}", exc_info=True)
    
    async def _check_all_models_health(self):
        """Check health of all models."""
        tasks = []
        for model_id in self.models.keys():
            tasks.append(self._check_model_health(model_id))
        
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _check_model_health(self, model_id: str) -> bool:
        """Check health of a specific model."""
        model = self.models[model_id]
        health_url = f"{model.endpoint}/health"
        
        try:
            async with httpx.AsyncClient(timeout=self.routing_config.timeouts['health_check']) as client:
                response = await client.get(health_url)
                
                if response.status_code == 200:
                    model.consecutive_successes += 1
                    model.consecutive_failures = 0
                    
                    if model.consecutive_successes >= self.healthy_threshold:
                        if not model.health_status:
                            logger.info(f"Model {model_id} is now healthy")
                            model.health_status = True
                            self.metrics.model_health.labels(model=model_id).set(1)
                    
                    return True
                else:
                    raise httpx.HTTPError(f"Unhealthy status code: {response.status_code}")
        
        except Exception as e:
            model.consecutive_failures += 1
            model.consecutive_successes = 0
            
            if model.consecutive_failures >= self.unhealthy_threshold:
                if model.health_status:
                    logger.warning(f"Model {model_id} is now unhealthy: {e}")
                    model.health_status = False
                    self.metrics.model_health.labels(model=model_id).set(0)
            
            return False
    
    def classify_intent(self, messages: List[Dict[str, str]]) -> Tuple[Intent, float]:
        """
        Classify intent from chat messages.
        
        Args:
            messages: List of chat messages
        
        Returns:
            Tuple of (intent, confidence)
        """
        start_time = time.time()
        
        # Combine all message content for classification
        combined_text = " ".join(
            msg.get('content', '') 
            for msg in messages 
            if msg.get('role') in ['user', 'system']
        )
        
        intent, confidence = self.intent_classifier.classify(combined_text)
        
        # Record metrics
        classification_time = time.time() - start_time
        self.metrics.classification_latency.observe(classification_time)
        
        confidence_label = 'high' if confidence >= 0.7 else 'medium' if confidence >= 0.4 else 'low'
        self.metrics.intent_classification.labels(
            intent=intent.value,
            confidence=confidence_label
        ).inc()
        
        logger.info(f"Classified intent: {intent.value} (confidence: {confidence:.2f})")
        
        return intent, confidence
    
    def select_model(self, intent: Intent) -> str:
        """
        Select primary model based on intent.
        
        Args:
            intent: Classified intent
        
        Returns:
            Model ID
        """
        model_id = self.routing_config.primary_model.get(intent.value, 'llama')
        logger.debug(f"Selected model {model_id} for intent {intent.value}")
        return model_id
    

    def get_routing_plan(self, intent: Intent) -> Dict[str, Any]:
        """Return primary model and fallback chain for a given intent."""
        primary_model_id = self.select_model(intent)
        return {
            "intent": intent.value,
            "primary_model": primary_model_id,
            "fallback_chain": self.get_fallback_chain(primary_model_id)
        }

    def get_fallback_chain(self, model_id: str) -> List[str]:
        """
        Get fallback chain for a model.
        
        Args:
            model_id: Primary model ID
        
        Returns:
            List of fallback model IDs
        """
        return self.routing_config.fallback_chains.get(model_id, [])
    
    async def generate(
        self,
        messages: List[Dict[str, str]],
        prompt: str,
        preferred_model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        stop: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Generate response with automatic model selection and fallback.
        
        Args:
            messages: Chat messages for intent classification
            prompt: Formatted prompt for generation
            max_tokens: Maximum tokens to generate (optional)
            temperature: Sampling temperature (optional)
            top_p: Nucleus sampling parameter (optional)
            stop: Stop sequences (optional)
        
        Returns:
            Generation result with metadata
        """
        start_time = time.time()
        
        # Classify intent
        intent, confidence = self.classify_intent(messages)
        
        # Select primary model
        primary_model_id = self.select_model(intent)
        explicit_model_used = False
        if preferred_model:
            resolved_model_id = self.resolve_model_identifier(preferred_model)
            if resolved_model_id:
                primary_model_id = resolved_model_id
                explicit_model_used = True
        
        # Try primary model first
        result = await self._try_model(
            model_id=primary_model_id,
            prompt=prompt,
            intent=intent,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            stop=stop
        )
        
        if result['success']:
            total_time = time.time() - start_time
            self.metrics.latency_seconds.labels(
                model=primary_model_id,
                intent=intent.value
            ).observe(total_time)
            
            result['metadata'] = {
                'model_id': primary_model_id,
                'model_name': self.models[primary_model_id].name,
                'intent': intent.value,
                'confidence': confidence,
                'fallback_used': False,
                'total_time_seconds': round(total_time, 3),
                'explicit_model_used': explicit_model_used
            }
            
            return result
        
        # Try fallback chain
        fallback_chain = self.get_fallback_chain(primary_model_id)
        logger.warning(f"Primary model {primary_model_id} failed, trying fallback chain: {fallback_chain}")
        
        for fallback_model_id in fallback_chain:
            self.metrics.fallback_requests.labels(
                from_model=primary_model_id,
                to_model=fallback_model_id
            ).inc()

            self.metrics.model_fallbacks.labels(
                model=primary_model_id,
                role='source'
            ).inc()
            self.metrics.model_fallbacks.labels(
                model=fallback_model_id,
                role='target'
            ).inc()
            
            result = await self._try_model(
                model_id=fallback_model_id,
                prompt=prompt,
                intent=intent,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                stop=stop
            )
            
            if result['success']:
                total_time = time.time() - start_time
                self.metrics.latency_seconds.labels(
                    model=fallback_model_id,
                    intent=intent.value
                ).observe(total_time)
                
                result['metadata'] = {
                    'model_id': fallback_model_id,
                    'model_name': self.models[fallback_model_id].name,
                    'intent': intent.value,
                    'confidence': confidence,
                    'fallback_used': True,
                    'primary_model': primary_model_id,
                    'total_time_seconds': round(total_time, 3),
                    'explicit_model_used': explicit_model_used
                }
                
                logger.info(f"Fallback successful with model {fallback_model_id}")
                return result
        
        # All models failed
        self.metrics.errors_total.labels(
            model='all',
            error_type='all_models_failed'
        ).inc()
        
        logger.error("All models failed")
        return {
            'success': False,
            'error': 'All models failed',
            'metadata': {
                'intent': intent.value,
                'confidence': confidence,
                'tried_models': [primary_model_id] + fallback_chain
            }
        }
    
    async def _try_model(
        self,
        model_id: str,
        prompt: str,
        intent: Intent,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        stop: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Try generating with a specific model using circuit breaker.
        
        Returns:
            Result dictionary with success flag
        """
        model = self.models[model_id]
        circuit_breaker = self.circuit_breakers.get(model_id)
        
        # Check health status
        if not model.health_status:
            logger.warning(f"Skipping unhealthy model {model_id}")
            self.metrics.errors_total.labels(
                model=model_id,
                error_type='unhealthy'
            ).inc()
            return {'success': False, 'error': 'Model unhealthy'}
        
        # Record request
        self.metrics.model_requests.labels(model=model_id).inc()
        
        # Prepare payload
        payload = {
            'prompt': prompt,
            'max_tokens': max_tokens or model.max_tokens,
            'temperature': temperature if temperature is not None else model.temperature,
            'top_p': top_p or 0.9,
            'stop': stop or ['<|eot_id|>', '<|end_of_text|>']
        }
        
        # Try with retries and circuit breaker protection
        max_attempts = self.routing_config.retry['max_attempts']
        backoff_factor = self.routing_config.retry['backoff_factor']
        
        async def make_request():
            """Inner function for circuit breaker."""
            generate_url = f"{model.endpoint}/generate"
            async with httpx.AsyncClient() as client:
                response = await client.post(generate_url, json=payload)
                response.raise_for_status()
                return response.json()
        
        for attempt in range(max_attempts):
            try:
                # Use circuit breaker for the request
                if circuit_breaker:
                    result = await circuit_breaker.call(make_request)
                else:
                    result = await make_request()
                
                # Success
                self.metrics.requests_total.labels(
                    model=model_id,
                    intent=intent.value,
                    status='success'
                ).inc()
                
                return {
                    'success': True,
                    'text': result.get('text', ''),
                    'model_id': model_id
                }
            
            except CircuitBreakerError as e:
                logger.warning(f"Circuit breaker open for {model_id}: {e}")
                self.metrics.errors_total.labels(
                    model=model_id,
                    error_type='circuit_breaker_open'
                ).inc()
                return {'success': False, 'error': 'Circuit breaker open'}
            
            except (httpx.HTTPError, asyncio.TimeoutError) as e:
                error_type = type(e).__name__
                self.metrics.errors_total.labels(
                    model=model_id,
                    error_type=error_type
                ).inc()
                
                logger.warning(f"Attempt {attempt + 1}/{max_attempts} failed for {model_id}: {e}")
                
                if attempt < max_attempts - 1:
                    await asyncio.sleep(backoff_factor ** attempt)
            
            except Exception as e:
                self.metrics.errors_total.labels(
                    model=model_id,
                    error_type='unexpected'
                ).inc()
                
                logger.error(f"Unexpected error for {model_id}: {e}", exc_info=True)
                break
        
        # All attempts failed
        self.metrics.requests_total.labels(
            model=model_id,
            intent=intent.value,
            status='failed'
        ).inc()
        
        return {'success': False, 'error': 'All retry attempts failed'}
    
    def get_model_info(self, model_id: str) -> Optional[ModelConfig]:
        """Get model configuration."""
        return self.models.get(model_id)
    
    def list_models(self) -> Dict[str, Dict[str, Any]]:
        """List all available models with their status."""
        return {
            model_id: {
                'name': model.name,
                'endpoint': model.endpoint,
                'description': model.description,
                'capabilities': model.capabilities,
                'health_status': model.health_status,
                'max_tokens': model.max_tokens,
                'temperature': model.temperature,
                'aliases': model.aliases
            }
            for model_id, model in self.models.items()
        }

    def resolve_model_identifier(self, model_identifier: str) -> Optional[str]:
        """Resolve model ID/name/alias to internal model ID."""
        return self.model_aliases.get(model_identifier.lower())
