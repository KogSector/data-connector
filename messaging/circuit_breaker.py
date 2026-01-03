"""
Circuit Breaker Pattern Implementation - DSA/Design Pattern
============================================================

Prevents cascading failures by stopping requests to failing services.
Uses exponential backoff for recovery attempts.

States:
- CLOSED: Normal operation, requests pass through
- OPEN: Failure threshold exceeded, requests blocked
- HALF_OPEN: Testing if service has recovered
"""

import time
import threading
import random
from enum import Enum
from typing import Callable, Optional, TypeVar
from dataclasses import dataclass
from collections import deque
import logging

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Blocking requests
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitStats:
    """Statistics for circuit breaker monitoring"""
    state: CircuitState
    failures: int
    successes: int
    total_requests: int
    last_failure_time: Optional[float]
    next_retry_time: Optional[float]
    consecutive_successes: int


class CircuitBreaker:
    """
    Circuit breaker with exponential backoff and jitter.
    
    Example:
        breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=30.0,
            half_open_max_calls=3,
        )
        
        @breaker
        def call_external_service():
            # This will be protected by the circuit breaker
            return requests.get("http://service/api")
        
        # Or use context manager
        with breaker:
            result = call_external_service()
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 3,
        exponential_backoff: bool = True,
        max_backoff: float = 300.0,  # 5 minutes
        failure_window: float = 60.0,  # Window to count failures
    ):
        """
        Initialize circuit breaker.
        
        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Base seconds before attempting recovery
            half_open_max_calls: Calls to allow in half-open state
            exponential_backoff: Use exponential backoff for recovery
            max_backoff: Maximum backoff time in seconds
            failure_window: Time window for counting failures
        """
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._half_open_max_calls = half_open_max_calls
        self._exponential_backoff = exponential_backoff
        self._max_backoff = max_backoff
        self._failure_window = failure_window
        
        self._state = CircuitState.CLOSED
        self._failures = 0
        self._successes = 0
        self._total_requests = 0
        self._consecutive_successes = 0
        self._half_open_calls = 0
        
        # Sliding window for failures (using deque for O(1) operations)
        self._failure_times: deque = deque()
        
        self._last_failure_time: Optional[float] = None
        self._next_retry_time: Optional[float] = None
        self._retry_count = 0
        
        self._lock = threading.Lock()
    
    @property
    def state(self) -> CircuitState:
        return self._state
    
    @property
    def is_open(self) -> bool:
        return self._state == CircuitState.OPEN
    
    def _count_recent_failures(self) -> int:
        """Count failures within the sliding window"""
        now = time.time()
        cutoff = now - self._failure_window
        
        # Remove old failures from window
        while self._failure_times and self._failure_times[0] < cutoff:
            self._failure_times.popleft()
        
        return len(self._failure_times)
    
    def _calculate_backoff(self) -> float:
        """
        Calculate backoff time with exponential increase and jitter.
        
        Uses: delay = min(base * 2^retry, max) * (0.5 + random(0, 0.5))
        """
        if not self._exponential_backoff:
            return self._recovery_timeout
        
        base_delay = self._recovery_timeout * (2 ** self._retry_count)
        capped_delay = min(base_delay, self._max_backoff)
        
        # Add jitter (50-100% of delay) to prevent thundering herd
        jitter = 0.5 + random.random() * 0.5
        return capped_delay * jitter
    
    def _transition_to(self, new_state: CircuitState):
        """Transition to a new state"""
        old_state = self._state
        self._state = new_state
        
        if new_state == CircuitState.OPEN:
            backoff = self._calculate_backoff()
            self._next_retry_time = time.time() + backoff
            self._retry_count += 1
            logger.warning(
                f"Circuit OPENED after {self._failures} failures. "
                f"Retry in {backoff:.1f}s"
            )
        elif new_state == CircuitState.HALF_OPEN:
            self._half_open_calls = 0
            logger.info("Circuit HALF-OPEN, testing recovery...")
        elif new_state == CircuitState.CLOSED:
            self._retry_count = 0
            self._failures = 0
            self._failure_times.clear()
            self._consecutive_successes = 0
            logger.info("Circuit CLOSED, normal operation resumed")
    
    def record_success(self):
        """Record a successful call"""
        with self._lock:
            self._successes += 1
            self._total_requests += 1
            self._consecutive_successes += 1
            
            if self._state == CircuitState.HALF_OPEN:
                self._half_open_calls += 1
                if self._half_open_calls >= self._half_open_max_calls:
                    self._transition_to(CircuitState.CLOSED)
    
    def record_failure(self, exception: Optional[Exception] = None):
        """Record a failed call"""
        with self._lock:
            now = time.time()
            self._failures += 1
            self._total_requests += 1
            self._consecutive_successes = 0
            self._last_failure_time = now
            self._failure_times.append(now)
            
            if self._state == CircuitState.HALF_OPEN:
                # Single failure in half-open triggers open
                self._transition_to(CircuitState.OPEN)
            elif self._state == CircuitState.CLOSED:
                # Check if we exceeded threshold in window
                recent_failures = self._count_recent_failures()
                if recent_failures >= self._failure_threshold:
                    self._transition_to(CircuitState.OPEN)
    
    def allow_request(self) -> bool:
        """Check if request should be allowed through"""
        with self._lock:
            if self._state == CircuitState.CLOSED:
                return True
            
            if self._state == CircuitState.OPEN:
                now = time.time()
                if self._next_retry_time and now >= self._next_retry_time:
                    self._transition_to(CircuitState.HALF_OPEN)
                    return True
                return False
            
            # Half-open: allow limited requests
            return self._half_open_calls < self._half_open_max_calls
    
    def execute(self, func: Callable[..., T], *args, **kwargs) -> T:
        """
        Execute function with circuit breaker protection.
        
        Raises:
            CircuitOpenError: If circuit is open
        """
        if not self.allow_request():
            raise CircuitOpenError(
                f"Circuit is OPEN. Retry after {self._next_retry_time - time.time():.1f}s"
            )
        
        try:
            result = func(*args, **kwargs)
            self.record_success()
            return result
        except Exception as e:
            self.record_failure(e)
            raise
    
    def __call__(self, func: Callable[..., T]) -> Callable[..., T]:
        """Decorator usage"""
        def wrapper(*args, **kwargs):
            return self.execute(func, *args, **kwargs)
        return wrapper
    
    def __enter__(self):
        if not self.allow_request():
            raise CircuitOpenError("Circuit is OPEN")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.record_failure(exc_val)
        else:
            self.record_success()
        return False  # Don't suppress exceptions
    
    def get_stats(self) -> CircuitStats:
        """Get current circuit breaker statistics"""
        with self._lock:
            return CircuitStats(
                state=self._state,
                failures=self._failures,
                successes=self._successes,
                total_requests=self._total_requests,
                last_failure_time=self._last_failure_time,
                next_retry_time=self._next_retry_time,
                consecutive_successes=self._consecutive_successes,
            )
    
    def reset(self):
        """Manually reset circuit to closed state"""
        with self._lock:
            self._transition_to(CircuitState.CLOSED)


class CircuitOpenError(Exception):
    """Raised when circuit is open and request is blocked"""
    pass


class MessageRouter:
    """
    Routes messages through circuit breakers to destinations.
    Each destination has its own circuit breaker.
    """
    
    def __init__(self):
        self._breakers: dict[str, CircuitBreaker] = {}
        self._lock = threading.Lock()
    
    def get_breaker(self, destination: str) -> CircuitBreaker:
        """Get or create circuit breaker for destination"""
        with self._lock:
            if destination not in self._breakers:
                self._breakers[destination] = CircuitBreaker()
            return self._breakers[destination]
    
    def route(
        self,
        destination: str,
        send_func: Callable,
        message: any,
    ) -> bool:
        """
        Route message through circuit breaker.
        
        Returns:
            True if message was sent, False if circuit is open
        """
        breaker = self.get_breaker(destination)
        
        try:
            breaker.execute(send_func, message)
            return True
        except CircuitOpenError:
            logger.warning(f"Message to {destination} blocked - circuit open")
            return False
    
    def get_all_stats(self) -> dict:
        """Get stats for all destinations"""
        return {dest: breaker.get_stats() for dest, breaker in self._breakers.items()}
