#!/usr/bin/env python3
"""
Example tests for circuit breaker and fallback chain implementation.

Run with: pytest test_circuit_breaker_example.py -v
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerError,
    CircuitState,
    get_circuit_breaker,
    get_all_circuit_breaker_stats
)
from fallback_chain import FallbackChain


class TestCircuitBreaker:
    """Test circuit breaker functionality."""
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_starts_closed(self):
        """Test circuit breaker starts in CLOSED state."""
        breaker = CircuitBreaker("test", CircuitBreakerConfig())
        assert breaker.state == CircuitState.CLOSED
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_after_failures(self):
        """Test circuit breaker opens after threshold failures."""
        breaker = CircuitBreaker(
            "test",
            CircuitBreakerConfig(failure_threshold=2, timeout_seconds=1.0)
        )
        
        async def failing_function():
            raise Exception("Service unavailable")
        
        # First failure
        with pytest.raises(Exception):
            await breaker.call(failing_function)
        assert breaker.state == CircuitState.CLOSED
        
        # Second failure - should open circuit
        with pytest.raises(Exception):
            await breaker.call(failing_function)
        assert breaker.state == CircuitState.OPEN
        
        # Third call should be rejected immediately
        with pytest.raises(CircuitBreakerError):
            await breaker.call(failing_function)
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_timeout(self):
        """Test circuit breaker respects timeout."""
        breaker = CircuitBreaker(
            "test",
            CircuitBreakerConfig(failure_threshold=1, timeout_seconds=0.1)
        )
        
        async def slow_function():
            await asyncio.sleep(1.0)
            return "success"
        
        with pytest.raises(asyncio.TimeoutError):
            await breaker.call(slow_function)
        
        assert breaker.state == CircuitState.OPEN
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_half_open_transition(self):
        """Test circuit breaker transitions to HALF_OPEN after recovery time."""
        breaker = CircuitBreaker(
            "test",
            CircuitBreakerConfig(
                failure_threshold=1,
                timeout_seconds=1.0,
                recovery_timeout_seconds=0.1  # Short recovery for testing
            )
        )
        
        async def failing_function():
            raise Exception("Fail")
        
        # Open the circuit
        with pytest.raises(Exception):
            await breaker.call(failing_function)
        assert breaker.state == CircuitState.OPEN
        
        # Wait for recovery timeout
        await asyncio.sleep(0.2)
        
        # Next call should transition to HALF_OPEN
        async def success_function():
            return "success"
        
        result = await breaker.call(success_function)
        assert result == "success"
        # After one success, still HALF_OPEN (needs 2 by default)
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_successful_call(self):
        """Test successful calls keep circuit CLOSED."""
        breaker = CircuitBreaker("test", CircuitBreakerConfig())
        
        async def success_function():
            return "success"
        
        for _ in range(10):
            result = await breaker.call(success_function)
            assert result == "success"
            assert breaker.state == CircuitState.CLOSED
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_statistics(self):
        """Test circuit breaker collects statistics."""
        breaker = CircuitBreaker("test", CircuitBreakerConfig())
        
        async def success_function():
            return "success"
        
        # Make some successful calls
        for _ in range(5):
            await breaker.call(success_function)
        
        stats = breaker.get_stats()
        assert stats["total_requests"] == 5
        assert stats["total_successes"] == 5
        assert stats["total_failures"] == 0
        assert stats["state"] == "closed"
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_reset(self):
        """Test manual circuit breaker reset."""
        breaker = CircuitBreaker(
            "test",
            CircuitBreakerConfig(failure_threshold=1)
        )
        
        async def failing_function():
            raise Exception("Fail")
        
        # Open the circuit
        with pytest.raises(Exception):
            await breaker.call(failing_function)
        assert breaker.state == CircuitState.OPEN
        
        # Reset
        breaker.reset()
        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0
    
    def test_circuit_breaker_registry(self):
        """Test circuit breaker registry."""
        # Get a breaker
        breaker1 = get_circuit_breaker("service1")
        assert breaker1.name == "service1"
        
        # Get same breaker again
        breaker2 = get_circuit_breaker("service1")
        assert breaker1 is breaker2
        
        # Get different breaker
        breaker3 = get_circuit_breaker("service2")
        assert breaker3 is not breaker1
        
        # Get all stats
        stats = get_all_circuit_breaker_stats()
        assert "service1" in stats
        assert "service2" in stats


class TestFallbackChain:
    """Test fallback chain functionality."""
    
    @pytest.mark.asyncio
    async def test_fallback_chain_max_gpu_success(self):
        """Test fallback chain uses MAX GPU when available."""
        with patch('fallback_chain.httpx.AsyncClient') as mock_client:
            # Mock successful MAX GPU response
            mock_response = MagicMock()
            mock_response.json.return_value = {"text": "GPU response"}
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()
            
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )
            
            chain = FallbackChain(
                max_gpu_endpoint="http://fake:8080",
                degraded_message="Degraded"
            )
            
            result = await chain.generate("test prompt")
            
            assert result["success"] is True
            assert result["tier_used"] == "max_gpu"
            assert result["text"] == "GPU response"
    
    @pytest.mark.asyncio
    async def test_fallback_chain_ollama_fallback(self):
        """Test fallback to Ollama when MAX GPU fails."""
        with patch('fallback_chain.httpx.AsyncClient') as mock_client:
            # Mock MAX GPU failure
            mock_max_response = MagicMock()
            mock_max_response.raise_for_status.side_effect = httpx.HTTPError("GPU down")
            
            # Mock Ollama success
            mock_ollama_response = MagicMock()
            mock_ollama_response.json.return_value = {"response": "Ollama response"}
            mock_ollama_response.status_code = 200
            mock_ollama_response.raise_for_status = MagicMock()
            
            # Return different responses for different endpoints
            async def mock_post(url, json):
                if "8080" in url:
                    return mock_max_response
                elif "11434" in url:
                    return mock_ollama_response
            
            mock_client.return_value.__aenter__.return_value.post = mock_post
            
            chain = FallbackChain(
                max_gpu_endpoint="http://fake:8080",
                ollama_cpu_endpoint="http://fake:11434",
                degraded_message="Degraded"
            )
            
            result = await chain.generate("test prompt")
            
            assert result["success"] is True
            assert result["tier_used"] == "ollama_cpu"
            assert result["text"] == "Ollama response"
    
    @pytest.mark.asyncio
    async def test_fallback_chain_cache_hit(self):
        """Test fallback chain uses cache when available."""
        import redis
        
        mock_redis = MagicMock(spec=redis.Redis)
        mock_redis.get.return_value = b"Cached response"
        
        with patch('fallback_chain.httpx.AsyncClient') as mock_client:
            # Mock all service failures
            mock_response = MagicMock()
            mock_response.raise_for_status.side_effect = httpx.HTTPError("Down")
            
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )
            
            chain = FallbackChain(
                max_gpu_endpoint="http://fake:8080",
                ollama_cpu_endpoint="http://fake:11434",
                redis_client=mock_redis,
                degraded_message="Degraded"
            )
            
            result = await chain.generate("test prompt")
            
            assert result["success"] is True
            assert result["tier_used"] == "cache"
            assert result["text"] == "Cached response"
    
    @pytest.mark.asyncio
    async def test_fallback_chain_degraded_message(self):
        """Test fallback chain returns degraded message when all fail."""
        import redis
        
        mock_redis = MagicMock(spec=redis.Redis)
        mock_redis.get.return_value = None  # Cache miss
        
        with patch('fallback_chain.httpx.AsyncClient') as mock_client:
            # Mock all service failures
            mock_response = MagicMock()
            mock_response.raise_for_status.side_effect = httpx.HTTPError("Down")
            
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )
            
            chain = FallbackChain(
                max_gpu_endpoint="http://fake:8080",
                ollama_cpu_endpoint="http://fake:11434",
                redis_client=mock_redis,
                degraded_message="Service unavailable"
            )
            
            result = await chain.generate("test prompt")
            
            assert result["success"] is False
            assert result["tier_used"] == "degraded"
            assert result["text"] == "Service unavailable"
    
    @pytest.mark.asyncio
    async def test_fallback_chain_statistics(self):
        """Test fallback chain collects statistics."""
        with patch('fallback_chain.httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = {"text": "response"}
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()
            
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )
            
            chain = FallbackChain(
                max_gpu_endpoint="http://fake:8080",
                degraded_message="Degraded"
            )
            
            # Make several requests
            for _ in range(5):
                await chain.generate("test")
            
            stats = chain.get_stats()
            assert stats["total_requests"] == 5
            assert stats["max_gpu_success"] == 5
            assert stats["max_gpu_failure"] == 0


class TestIntegration:
    """Integration tests combining circuit breaker and fallback chain."""
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_in_fallback_chain(self):
        """Test circuit breaker integration in fallback chain."""
        with patch('fallback_chain.httpx.AsyncClient') as mock_client:
            # Simulate consistent failures to open circuit breaker
            call_count = [0]
            
            async def mock_post(url, json):
                call_count[0] += 1
                mock_response = MagicMock()
                mock_response.raise_for_status.side_effect = httpx.HTTPError("Service down")
                return mock_response
            
            mock_client.return_value.__aenter__.return_value.post = mock_post
            
            chain = FallbackChain(
                max_gpu_endpoint="http://fake:8080",
                degraded_message="Unavailable"
            )
            
            # Make requests until circuit breaker opens
            for i in range(5):
                result = await chain.generate("test")
                assert result["tier_used"] == "degraded"
            
            # Circuit breaker should have opened, reducing actual HTTP calls
            stats = chain.get_stats()
            assert stats["total_requests"] == 5
            assert stats["degraded_response"] == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
