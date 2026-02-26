#!/usr/bin/env python3
"""Basic test for circuit breaker without external dependencies."""

import asyncio
from circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    CircuitBreakerError,
    get_circuit_breaker
)

print("Testing Circuit Breaker Implementation")
print("=" * 50)

# Test 1: Basic initialization
print("\n[Test 1] Circuit breaker initialization...")
breaker = CircuitBreaker(
    "test_service",
    CircuitBreakerConfig(
        failure_threshold=3,
        timeout_seconds=5.0,
        recovery_timeout_seconds=30.0
    )
)
assert breaker.state == CircuitState.CLOSED, "Should start CLOSED"
print("✓ Circuit breaker starts in CLOSED state")

# Test 2: Successful call
print("\n[Test 2] Successful call...")
async def test_success():
    async def success_func():
        return "success"
    
    result = await breaker.call(success_func)
    assert result == "success"
    assert breaker.state == CircuitState.CLOSED
    print("✓ Successful call keeps circuit CLOSED")

asyncio.run(test_success())

# Test 3: Failure opens circuit
print("\n[Test 3] Failures open circuit...")
async def test_failures():
    breaker2 = CircuitBreaker(
        "test_failures",
        CircuitBreakerConfig(failure_threshold=2, timeout_seconds=1.0)
    )
    
    async def failing_func():
        raise Exception("Service down")
    
    # First failure
    try:
        await breaker2.call(failing_func)
    except Exception:
        pass
    assert breaker2.state == CircuitState.CLOSED, "Should still be CLOSED after 1 failure"
    
    # Second failure - should open
    try:
        await breaker2.call(failing_func)
    except Exception:
        pass
    assert breaker2.state == CircuitState.OPEN, "Should be OPEN after 2 failures"
    print("✓ Circuit opens after failure threshold")
    
    # Third call should be rejected
    try:
        await breaker2.call(failing_func)
        assert False, "Should have raised CircuitBreakerError"
    except CircuitBreakerError:
        print("✓ Circuit rejects calls when OPEN")

asyncio.run(test_failures())

# Test 4: Statistics
print("\n[Test 4] Statistics tracking...")
stats = breaker.get_stats()
assert "total_requests" in stats
assert "total_successes" in stats
assert "total_failures" in stats
assert "state" in stats
print(f"✓ Statistics tracked: {stats['total_requests']} requests")

# Test 5: Registry
print("\n[Test 5] Circuit breaker registry...")
cb1 = get_circuit_breaker("service1")
cb2 = get_circuit_breaker("service1")
assert cb1 is cb2, "Registry should return same instance"
print("✓ Registry returns same instance for same name")

# Test 6: Reset
print("\n[Test 6] Manual reset...")
breaker_reset = CircuitBreaker("test_reset", CircuitBreakerConfig(failure_threshold=1))
async def test_reset():
    async def fail():
        raise Exception("fail")
    
    try:
        await breaker_reset.call(fail)
    except:
        pass
    
    assert breaker_reset.state == CircuitState.OPEN
    breaker_reset.reset()
    assert breaker_reset.state == CircuitState.CLOSED
    print("✓ Manual reset works")

asyncio.run(test_reset())

print("\n" + "=" * 50)
print("✓ All circuit breaker tests passed!")
print("✓ Implementation is working correctly")
print("\nConfiguration:")
print(f"  - Failure Threshold: 3")
print(f"  - Timeout: 5 seconds")
print(f"  - Recovery Period: 30 seconds")
print(f"  - Success Threshold: 2")
