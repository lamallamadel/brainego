#!/usr/bin/env python3
"""
Fallback chain implementation for multi-tier service degradation.

Fallback order: MAX GPU -> Ollama CPU -> Cache -> Degraded message
"""

import logging
import hashlib
import json
from typing import Optional, Dict, Any, List, Callable
from datetime import datetime
import httpx
import redis

from circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitBreakerError

logger = logging.getLogger(__name__)


class FallbackChain:
    """
    Manages fallback chain for inference requests.
    
    Chain: MAX GPU -> Ollama CPU -> Cache -> Degraded Message
    
    Each tier is protected by a circuit breaker to avoid cascading failures.
    """
    
    def __init__(
        self,
        max_gpu_endpoint: str,
        ollama_cpu_endpoint: Optional[str] = None,
        redis_client: Optional[redis.Redis] = None,
        degraded_message: str = "Service temporarily unavailable. Please try again later.",
        circuit_breaker_config: Optional[CircuitBreakerConfig] = None
    ):
        """
        Initialize fallback chain.
        
        Args:
            max_gpu_endpoint: MAX Serve GPU endpoint
            ollama_cpu_endpoint: Ollama CPU endpoint (optional)
            redis_client: Redis client for caching (optional)
            degraded_message: Message to return when all tiers fail
            circuit_breaker_config: Circuit breaker configuration
        """
        self.max_gpu_endpoint = max_gpu_endpoint
        self.ollama_cpu_endpoint = ollama_cpu_endpoint
        self.redis_client = redis_client
        self.degraded_message = degraded_message
        
        # Circuit breaker configuration
        cb_config = circuit_breaker_config or CircuitBreakerConfig(
            failure_threshold=3,
            timeout_seconds=5.0,
            recovery_timeout_seconds=30.0,
            success_threshold=2
        )
        
        # Create circuit breakers for each tier
        from circuit_breaker import get_circuit_breaker
        self.max_gpu_breaker = get_circuit_breaker("max_gpu", cb_config)
        
        if ollama_cpu_endpoint:
            self.ollama_cpu_breaker = get_circuit_breaker("ollama_cpu", cb_config)
        else:
            self.ollama_cpu_breaker = None
        
        # Statistics
        self.stats = {
            "max_gpu_success": 0,
            "max_gpu_failure": 0,
            "ollama_cpu_success": 0,
            "ollama_cpu_failure": 0,
            "cache_hit": 0,
            "cache_miss": 0,
            "degraded_response": 0,
            "total_requests": 0
        }
        
        logger.info(
            f"Fallback chain initialized: MAX GPU ({max_gpu_endpoint}) -> "
            f"Ollama CPU ({ollama_cpu_endpoint or 'disabled'}) -> "
            f"Cache ({'enabled' if redis_client else 'disabled'}) -> "
            f"Degraded message"
        )
    
    def _get_cache_key(self, prompt: str, params: Dict[str, Any]) -> str:
        """Generate cache key from prompt and parameters."""
        # Create deterministic key from prompt and relevant params
        cache_input = {
            "prompt": prompt[:1000],  # Limit prompt length for key
            "max_tokens": params.get("max_tokens"),
            "temperature": params.get("temperature"),
            "top_p": params.get("top_p")
        }
        key_str = json.dumps(cache_input, sort_keys=True)
        return f"llm_cache:{hashlib.sha256(key_str.encode()).hexdigest()}"
    
    async def _try_max_gpu(self, prompt: str, params: Dict[str, Any]) -> Optional[str]:
        """Try MAX GPU inference."""
        async def call_max_gpu():
            url = f"{self.max_gpu_endpoint}/generate"
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json={
                    "prompt": prompt,
                    **params
                })
                response.raise_for_status()
                result = response.json()
                return result.get("text", "").strip()
        
        try:
            text = await self.max_gpu_breaker.call(call_max_gpu)
            self.stats["max_gpu_success"] += 1
            logger.info("Fallback chain: MAX GPU success")
            return text
        except CircuitBreakerError as e:
            logger.warning(f"Fallback chain: MAX GPU circuit breaker open: {e}")
            self.stats["max_gpu_failure"] += 1
            return None
        except Exception as e:
            logger.warning(f"Fallback chain: MAX GPU failed: {e}")
            self.stats["max_gpu_failure"] += 1
            return None
    
    async def _try_ollama_cpu(self, prompt: str, params: Dict[str, Any]) -> Optional[str]:
        """Try Ollama CPU inference."""
        if not self.ollama_cpu_endpoint or not self.ollama_cpu_breaker:
            return None
        
        async def call_ollama():
            url = f"{self.ollama_cpu_endpoint}/api/generate"
            # Convert to Ollama API format
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json={
                    "model": "llama3.2",  # Default model
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "num_predict": params.get("max_tokens", 2048),
                        "temperature": params.get("temperature", 0.7),
                        "top_p": params.get("top_p", 0.9)
                    }
                })
                response.raise_for_status()
                result = response.json()
                return result.get("response", "").strip()
        
        try:
            text = await self.ollama_cpu_breaker.call(call_ollama)
            self.stats["ollama_cpu_success"] += 1
            logger.info("Fallback chain: Ollama CPU success")
            return text
        except CircuitBreakerError as e:
            logger.warning(f"Fallback chain: Ollama CPU circuit breaker open: {e}")
            self.stats["ollama_cpu_failure"] += 1
            return None
        except Exception as e:
            logger.warning(f"Fallback chain: Ollama CPU failed: {e}")
            self.stats["ollama_cpu_failure"] += 1
            return None
    
    def _try_cache(self, prompt: str, params: Dict[str, Any]) -> Optional[str]:
        """Try to get response from cache."""
        if not self.redis_client:
            return None
        
        try:
            cache_key = self._get_cache_key(prompt, params)
            cached = self.redis_client.get(cache_key)
            
            if cached:
                self.stats["cache_hit"] += 1
                logger.info("Fallback chain: Cache hit")
                return cached.decode('utf-8')
            else:
                self.stats["cache_miss"] += 1
                return None
        except Exception as e:
            logger.warning(f"Fallback chain: Cache lookup failed: {e}")
            self.stats["cache_miss"] += 1
            return None
    
    def _cache_response(self, prompt: str, params: Dict[str, Any], response: str):
        """Cache a successful response."""
        if not self.redis_client:
            return
        
        try:
            cache_key = self._get_cache_key(prompt, params)
            # Cache for 1 hour
            self.redis_client.setex(cache_key, 3600, response.encode('utf-8'))
            logger.debug(f"Cached response for key: {cache_key[:32]}...")
        except Exception as e:
            logger.warning(f"Failed to cache response: {e}")
    
    async def generate(
        self,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        top_p: float = 0.9,
        stop: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Generate response using fallback chain.
        
        Order of attempts:
        1. MAX GPU (with circuit breaker)
        2. Ollama CPU (with circuit breaker, if configured)
        3. Cache (if available)
        4. Degraded message
        
        Args:
            prompt: Input prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            top_p: Nucleus sampling parameter
            stop: Stop sequences
            
        Returns:
            Dict with 'text', 'tier_used', and 'success' keys
        """
        self.stats["total_requests"] += 1
        
        params = {
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "stop": stop or []
        }
        
        # Tier 1: Try MAX GPU
        text = await self._try_max_gpu(prompt, params)
        if text:
            self._cache_response(prompt, params, text)
            return {
                "text": text,
                "tier_used": "max_gpu",
                "success": True,
                "cached": False
            }
        
        # Tier 2: Try Ollama CPU
        text = await self._try_ollama_cpu(prompt, params)
        if text:
            self._cache_response(prompt, params, text)
            return {
                "text": text,
                "tier_used": "ollama_cpu",
                "success": True,
                "cached": False
            }
        
        # Tier 3: Try cache
        text = self._try_cache(prompt, params)
        if text:
            return {
                "text": text,
                "tier_used": "cache",
                "success": True,
                "cached": True
            }
        
        # Tier 4: Return degraded message
        self.stats["degraded_response"] += 1
        logger.error("Fallback chain: All tiers failed, returning degraded message")
        return {
            "text": self.degraded_message,
            "tier_used": "degraded",
            "success": False,
            "cached": False
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """Get fallback chain statistics."""
        total = self.stats["total_requests"]
        
        stats = {
            **self.stats,
            "success_rate": round(
                (self.stats["max_gpu_success"] + self.stats["ollama_cpu_success"]) / max(total, 1) * 100,
                2
            ),
            "cache_hit_rate": round(
                self.stats["cache_hit"] / max(self.stats["cache_hit"] + self.stats["cache_miss"], 1) * 100,
                2
            ) if (self.stats["cache_hit"] + self.stats["cache_miss"]) > 0 else 0,
            "degraded_rate": round(
                self.stats["degraded_response"] / max(total, 1) * 100,
                2
            )
        }
        
        # Add circuit breaker stats
        stats["max_gpu_breaker"] = self.max_gpu_breaker.get_stats()
        if self.ollama_cpu_breaker:
            stats["ollama_cpu_breaker"] = self.ollama_cpu_breaker.get_stats()
        
        return stats
    
    def reset_stats(self):
        """Reset statistics."""
        self.stats = {k: 0 for k in self.stats.keys()}
