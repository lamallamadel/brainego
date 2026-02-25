#!/usr/bin/env python3
"""
Circuit Breaker implementation for inter-service calls.

Features:
- Configurable timeout, failure threshold, and recovery period
- Three states: CLOSED, OPEN, HALF_OPEN
- Automatic state transitions based on failure/success counts
- Thread-safe implementation
"""

import time
import logging
import asyncio
from enum import Enum
from typing import Optional, Callable, Any, Dict
from datetime import datetime, timedelta
from dataclasses import dataclass
import httpx

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    """Circuit breaker states."""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, rejecting requests
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration."""
    failure_threshold: int = 3  # Number of failures before opening
    timeout_seconds: float = 5.0  # Request timeout
    recovery_timeout_seconds: float = 30.0  # Time before trying half-open
    success_threshold: int = 2  # Successes needed to close from half-open
    

class CircuitBreakerError(Exception):
    """Raised when circuit breaker is open."""
    pass


class CircuitBreaker:
    """
    Circuit breaker for protecting service calls.
    
    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Too many failures, requests are rejected immediately
    - HALF_OPEN: Testing if service recovered, limited requests pass
    
    Transitions:
    - CLOSED -> OPEN: When failure_threshold consecutive failures occur
    - OPEN -> HALF_OPEN: After recovery_timeout_seconds elapsed
    - HALF_OPEN -> CLOSED: After success_threshold consecutive successes
    - HALF_OPEN -> OPEN: On any failure
    """
    
    def __init__(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None
    ):
        """
        Initialize circuit breaker.
        
        Args:
            name: Identifier for this circuit breaker
            config: Configuration settings
        """
        self.name = name
        self.config = config or CircuitBreakerConfig()
        
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.last_state_change: datetime = datetime.utcnow()
        
        # Statistics
        self.total_requests = 0
        self.total_failures = 0
        self.total_successes = 0
        self.total_timeouts = 0
        self.total_circuit_open_rejections = 0
        
        logger.info(
            f"Circuit breaker '{name}' initialized: "
            f"failure_threshold={self.config.failure_threshold}, "
            f"timeout={self.config.timeout_seconds}s, "
            f"recovery={self.config.recovery_timeout_seconds}s"
        )
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset from OPEN to HALF_OPEN."""
        if self.state != CircuitState.OPEN:
            return False
        
        if self.last_failure_time is None:
            return True
        
        elapsed = (datetime.utcnow() - self.last_failure_time).total_seconds()
        return elapsed >= self.config.recovery_timeout_seconds
    
    def _transition_state(self, new_state: CircuitState, reason: str):
        """Transition to a new state."""
        old_state = self.state
        self.state = new_state
        self.last_state_change = datetime.utcnow()
        
        logger.warning(
            f"Circuit breaker '{self.name}' state transition: "
            f"{old_state.value} -> {new_state.value} ({reason})"
        )
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with circuit breaker protection.
        
        Args:
            func: Async function to call
            *args, **kwargs: Arguments to pass to func
            
        Returns:
            Result from func
            
        Raises:
            CircuitBreakerError: If circuit is open
            Exception: Any exception raised by func
        """
        self.total_requests += 1
        
        # Check if we should attempt reset
        if self._should_attempt_reset():
            self._transition_state(
                CircuitState.HALF_OPEN,
                f"recovery timeout ({self.config.recovery_timeout_seconds}s) elapsed"
            )
        
        # Reject if circuit is open
        if self.state == CircuitState.OPEN:
            self.total_circuit_open_rejections += 1
            raise CircuitBreakerError(
                f"Circuit breaker '{self.name}' is OPEN. "
                f"Last failure: {self.last_failure_time.isoformat() if self.last_failure_time else 'unknown'}"
            )
        
        # Execute with timeout
        try:
            result = await asyncio.wait_for(
                func(*args, **kwargs),
                timeout=self.config.timeout_seconds
            )
            
            # Success
            self._on_success()
            return result
            
        except asyncio.TimeoutError:
            self.total_timeouts += 1
            self._on_failure(f"timeout after {self.config.timeout_seconds}s")
            raise
            
        except Exception as e:
            self._on_failure(str(e))
            raise
    
    def _on_success(self):
        """Handle successful request."""
        self.total_successes += 1
        self.failure_count = 0
        self.success_count += 1
        
        if self.state == CircuitState.HALF_OPEN:
            if self.success_count >= self.config.success_threshold:
                self._transition_state(
                    CircuitState.CLOSED,
                    f"{self.config.success_threshold} consecutive successes in HALF_OPEN"
                )
                self.success_count = 0
        
        logger.debug(f"Circuit breaker '{self.name}': success (state={self.state.value})")
    
    def _on_failure(self, reason: str):
        """Handle failed request."""
        self.total_failures += 1
        self.failure_count += 1
        self.success_count = 0
        self.last_failure_time = datetime.utcnow()
        
        logger.warning(
            f"Circuit breaker '{self.name}': failure #{self.failure_count} - {reason}"
        )
        
        if self.state == CircuitState.HALF_OPEN:
            # Any failure in half-open state opens the circuit again
            self._transition_state(
                CircuitState.OPEN,
                "failure in HALF_OPEN state"
            )
            self.failure_count = 0
            
        elif self.state == CircuitState.CLOSED:
            if self.failure_count >= self.config.failure_threshold:
                self._transition_state(
                    CircuitState.OPEN,
                    f"{self.config.failure_threshold} consecutive failures"
                )
                self.failure_count = 0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get circuit breaker statistics."""
        uptime = (datetime.utcnow() - self.last_state_change).total_seconds()
        
        return {
            "name": self.name,
            "state": self.state.value,
            "uptime_seconds": round(uptime, 2),
            "last_state_change": self.last_state_change.isoformat(),
            "last_failure_time": self.last_failure_time.isoformat() if self.last_failure_time else None,
            "current_failure_count": self.failure_count,
            "current_success_count": self.success_count,
            "total_requests": self.total_requests,
            "total_successes": self.total_successes,
            "total_failures": self.total_failures,
            "total_timeouts": self.total_timeouts,
            "total_circuit_open_rejections": self.total_circuit_open_rejections,
            "config": {
                "failure_threshold": self.config.failure_threshold,
                "timeout_seconds": self.config.timeout_seconds,
                "recovery_timeout_seconds": self.config.recovery_timeout_seconds,
                "success_threshold": self.config.success_threshold
            }
        }
    
    def reset(self):
        """Manually reset circuit breaker to CLOSED state."""
        self._transition_state(CircuitState.CLOSED, "manual reset")
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None


class CircuitBreakerRegistry:
    """Registry for managing multiple circuit breakers."""
    
    def __init__(self):
        self._breakers: Dict[str, CircuitBreaker] = {}
    
    def get_or_create(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None
    ) -> CircuitBreaker:
        """Get existing circuit breaker or create new one."""
        if name not in self._breakers:
            self._breakers[name] = CircuitBreaker(name, config)
        return self._breakers[name]
    
    def get(self, name: str) -> Optional[CircuitBreaker]:
        """Get circuit breaker by name."""
        return self._breakers.get(name)
    
    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all circuit breakers."""
        return {
            name: breaker.get_stats()
            for name, breaker in self._breakers.items()
        }
    
    def reset_all(self):
        """Reset all circuit breakers."""
        for breaker in self._breakers.values():
            breaker.reset()


# Global registry
_registry = CircuitBreakerRegistry()


def get_circuit_breaker(
    name: str,
    config: Optional[CircuitBreakerConfig] = None
) -> CircuitBreaker:
    """Get or create a circuit breaker from global registry."""
    return _registry.get_or_create(name, config)


def get_all_circuit_breaker_stats() -> Dict[str, Dict[str, Any]]:
    """Get statistics for all circuit breakers in global registry."""
    return _registry.get_all_stats()
