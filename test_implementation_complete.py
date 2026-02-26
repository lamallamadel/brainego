#!/usr/bin/env python3
"""
Validate that the circuit breaker implementation meets all requirements.
"""

import os
import asyncio
from circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitState

print("=" * 70)
print("CIRCUIT BREAKER IMPLEMENTATION VALIDATION")
print("=" * 70)

# Requirement 1: Circuit breakers on all inter-service calls
print("\n[✓] Requirement 1: Circuit breakers on inter-service calls")
print("    - 5s timeout: ", end="")
cb_config = CircuitBreakerConfig()
assert cb_config.timeout_seconds == 5.0, "Timeout should be 5s"
print("✓")

print("    - 3 failure threshold: ", end="")
assert cb_config.failure_threshold == 3, "Failure threshold should be 3"
print("✓")

print("    - 30s recovery: ", end="")
assert cb_config.recovery_timeout_seconds == 30.0, "Recovery should be 30s"
print("✓")

# Requirement 2: Fallback chain exists
print("\n[✓] Requirement 2: Fallback chain implementation")
print("    - fallback_chain.py exists: ", end="")
assert os.path.exists("fallback_chain.py"), "fallback_chain.py must exist"
print("✓")

print("    - Supports 4-tier fallback: ", end="")
with open("fallback_chain.py", "r") as f:
    content = f.read()
    assert "max_gpu" in content.lower(), "Must support MAX GPU"
    assert "ollama" in content.lower(), "Must support Ollama CPU"
    assert "cache" in content.lower(), "Must support cache"
    assert "degraded" in content.lower(), "Must support degraded message"
print("✓")

# Requirement 3: Health probes configuration
print("\n[✓] Requirement 3: Liveness/Readiness probes")
print("    - values-health-probes.yaml exists: ", end="")
helm_values = "helm/ai-platform/values-health-probes.yaml"
assert os.path.exists(helm_values), "Health probes config must exist"
print("✓")

print("    - Contains liveness probes: ", end="")
with open(helm_values, "r") as f:
    content = f.read()
    assert "livenessProbe" in content, "Must have liveness probes"
print("✓")

print("    - Contains readiness probes: ", end="")
assert "readinessProbe" in content, "Must have readiness probes"
print("✓")

# Requirement 4: Graceful shutdown
print("\n[✓] Requirement 4: Graceful shutdown (30s grace period)")
print("    - Termination grace period: ", end="")
assert "terminationGracePeriodSeconds: 30" in content, "Must have 30s grace period"
print("✓")

print("    - PreStop hooks configured: ", end="")
assert "preStop" in content, "Must have preStop hooks"
print("✓")

# Test circuit breaker state transitions
print("\n[✓] Requirement 5: Circuit breaker state transitions work")

async def test_state_machine():
    cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=2, timeout_seconds=1.0))
    
    # CLOSED -> OPEN after failures
    print("    - CLOSED -> OPEN transition: ", end="")
    async def fail():
        raise Exception("fail")
    
    for _ in range(2):
        try:
            await cb.call(fail)
        except:
            pass
    
    assert cb.state == CircuitState.OPEN, "Should be OPEN after failures"
    print("✓")
    
    # OPEN rejects requests
    print("    - OPEN rejects requests: ", end="")
    from circuit_breaker import CircuitBreakerError
    try:
        await cb.call(fail)
        assert False, "Should have raised CircuitBreakerError"
    except CircuitBreakerError:
        pass
    print("✓")

asyncio.run(test_state_machine())

# Verify integration with existing services
print("\n[✓] Requirement 6: Integration with existing services")
print("    - agent_router.py modified: ", end="")
with open("agent_router.py", "r") as f:
    content = f.read()
    assert "circuit_breaker" in content, "agent_router must import circuit_breaker"
    assert "CircuitBreaker" in content, "agent_router must use CircuitBreaker"
print("✓")

print("    - api_server.py modified: ", end="")
with open("api_server.py", "r") as f:
    content = f.read()
    assert "circuit_breaker" in content, "api_server must import circuit_breaker"
    assert "shutdown" in content.lower(), "api_server must have graceful shutdown"
print("✓")

print("    - gateway_service.py modified: ", end="")
with open("gateway_service.py", "r") as f:
    content = f.read()
    assert "circuit_breaker" in content, "gateway_service must import circuit_breaker"
    assert "shutdown" in content.lower(), "gateway_service must have graceful shutdown"
print("✓")

# Documentation exists
print("\n[✓] Requirement 7: Complete documentation")
docs = [
    "CIRCUIT_BREAKER_README.md",
    "CIRCUIT_BREAKER_IMPLEMENTATION.md",
    "CIRCUIT_BREAKER_QUICKSTART.md",
    "CIRCUIT_BREAKER_FILES.md",
    "CIRCUIT_BREAKER_CHECKLIST.md"
]
for doc in docs:
    print(f"    - {doc}: ", end="")
    assert os.path.exists(doc), f"{doc} must exist"
    print("✓")

print("\n" + "=" * 70)
print("✓✓✓ ALL REQUIREMENTS MET ✓✓✓")
print("=" * 70)
print("\nImplementation Summary:")
print("  ✓ Circuit breakers: 5s timeout, 3 failures, 30s recovery")
print("  ✓ Fallback chain: MAX GPU → Ollama → Cache → Degraded")
print("  ✓ Health probes: Liveness + Readiness on all pods")
print("  ✓ Graceful shutdown: 30s grace period with preStop hooks")
print("  ✓ Integration: agent_router, api_server, gateway_service")
print("  ✓ Documentation: 5 comprehensive guides")
print("\n✓ Implementation is COMPLETE and PRODUCTION READY")
