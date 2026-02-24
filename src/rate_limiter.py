"""API rate limiter to prevent IP bans and runaway costs."""

import logging
from collections import deque
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class APIRateLimiter:
    """
    Rate limiter for API calls to prevent IP bans and runaway costs.

    Features:
    - Max calls per minute limit
    - Circuit breaker pattern (stops after consecutive failures)
    - Request queuing with backoff
    """

    def __init__(self, max_calls_per_minute: int = 10, circuit_breaker_threshold: int = 5):
        """
        Initialize rate limiter.

        Args:
            max_calls_per_minute: Maximum API calls allowed per minute
            circuit_breaker_threshold: Number of consecutive failures before circuit opens
        """
        self.max_calls_per_minute = max_calls_per_minute
        self.circuit_breaker_threshold = circuit_breaker_threshold

        # Track API call timestamps (sliding window)
        self.call_timestamps = deque(maxlen=max_calls_per_minute)

        # Circuit breaker state
        self.consecutive_failures = 0
        self.circuit_open = False
        self.circuit_open_until = None

        # Statistics
        self.total_calls = 0
        self.total_failures = 0
        self.total_rate_limited = 0

    def can_make_call(self) -> tuple[bool, float]:
        """
        Check if we can make an API call now.

        Returns:
            (can_call, wait_seconds) tuple
        """
        # Check circuit breaker
        if self.circuit_open:
            if datetime.now() < self.circuit_open_until:
                wait_seconds = (self.circuit_open_until - datetime.now()).total_seconds()
                return (False, wait_seconds)
            else:
                # Circuit breaker timeout expired, close circuit
                self._close_circuit()

        # Check rate limit (sliding window)
        now = datetime.now()

        # Remove calls older than 1 minute
        cutoff_time = now - timedelta(minutes=1)
        while self.call_timestamps and self.call_timestamps[0] < cutoff_time:
            self.call_timestamps.popleft()

        # Check if we have capacity
        if len(self.call_timestamps) >= self.max_calls_per_minute:
            # Calculate wait time until oldest call expires
            oldest_call = self.call_timestamps[0]
            wait_until = oldest_call + timedelta(minutes=1)
            wait_seconds = (wait_until - now).total_seconds()

            self.total_rate_limited += 1
            logger.warning(f"Rate limit reached: {len(self.call_timestamps)}/{self.max_calls_per_minute} calls. "
                          f"Wait {wait_seconds:.1f}s")
            return (False, wait_seconds)

        return (True, 0.0)

    def record_call(self, success: bool):
        """Record an API call and update circuit breaker state."""
        self.call_timestamps.append(datetime.now())
        self.total_calls += 1

        if success:
            self.consecutive_failures = 0
        else:
            self.consecutive_failures += 1
            self.total_failures += 1

            # Open circuit breaker if threshold reached
            if self.consecutive_failures >= self.circuit_breaker_threshold:
                self._open_circuit()

    def _open_circuit(self):
        """Open circuit breaker to prevent further calls."""
        self.circuit_open = True
        # Exponential backoff: 2^failures seconds (max 5 minutes)
        backoff_seconds = min(2 ** self.consecutive_failures, 300)
        self.circuit_open_until = datetime.now() + timedelta(seconds=backoff_seconds)

        logger.error(f"Circuit breaker OPEN: {self.consecutive_failures} consecutive failures. "
                    f"Blocked for {backoff_seconds}s")

    def _close_circuit(self):
        """Close circuit breaker to allow calls again."""
        self.circuit_open = False
        self.circuit_open_until = None
        logger.info("Circuit breaker CLOSED: Resuming API calls")

    def get_stats(self) -> dict:
        """Get rate limiter statistics."""
        return {
            'total_calls': self.total_calls,
            'total_failures': self.total_failures,
            'total_rate_limited': self.total_rate_limited,
            'consecutive_failures': self.consecutive_failures,
            'circuit_open': self.circuit_open,
            'current_calls_per_minute': len(self.call_timestamps),
            'max_calls_per_minute': self.max_calls_per_minute
        }
