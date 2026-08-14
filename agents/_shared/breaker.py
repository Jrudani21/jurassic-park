"""Circuit breaker for the shared LLM client (per-provider, no deps).

Prevents retry storms + billed-token bleed when a provider (DeepSeek/Ollama/
Groq) is down. Research-backed (2026-08-14 roadmap): one shared client + 30+
script agents means a provider outage currently amplifies into a coordinated
retry storm.

States:
  CLOSED   — normal; calls flow, failures counted
  OPEN     — fail fast (raise BreakerOpen) for cooldown; no calls attempted
  HALF_OPEN — after cooldown, probe with 1 call; success -> CLOSED,
              failure -> OPEN again

Failure = 429/5xx/timeout/network (transient-ish signals that a provider is
degraded). 4xx auth/config errors are NOT breaker material (permanent).
"""
from __future__ import annotations

import threading
import time


class BreakerOpen(Exception):
    """Raised when a provider circuit is open — fail fast, try next tier."""


class CircuitBreaker:
    def __init__(self, name: str, failure_threshold: int = 5,
                 cooldown_s: float = 60.0, half_open_max: int = 1):
        self.name = name
        self.failure_threshold = failure_threshold
        self.cooldown_s = cooldown_s
        self.half_open_max = half_open_max
        self._lock = threading.Lock()
        self._state = "closed"          # closed | open | half_open
        self._failures = 0
        self._opened_at = 0.0
        self._half_open_trials = 0

    @property
    def state(self) -> str:
        with self._lock:
            # auto half-open after cooldown
            if self._state == "open" and time.time() - self._opened_at >= self.cooldown_s:
                self._state = "half_open"
                self._half_open_trials = 0
            return self._state

    def allow(self) -> bool:
        st = self.state
        if st == "closed":
            return True
        if st == "half_open":
            with self._lock:
                if self._half_open_trials < self.half_open_max:
                    self._half_open_trials += 1
                    return True
                return False
        return False  # open

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0
            if self._state in ("open", "half_open"):
                self._state = "closed"

    def record_failure(self) -> None:
        with self._lock:
            if self._state == "half_open":
                self._state = "open"
                self._opened_at = time.time()
                self._half_open_trials = 0
                return
            self._failures += 1
            if self._failures >= self.failure_threshold:
                self._state = "open"
                self._opened_at = time.time()

    def reset(self) -> None:
        with self._lock:
            self._state = "closed"
            self._failures = 0
            self._opened_at = 0.0
            self._half_open_trials = 0

    def __repr__(self):
        return f"<CircuitBreaker {self.name} state={self.state} failures={self._failures}>"


# Shared per-provider breakers (keyed by tier name in llm.py)
_BREAKERS: dict[str, CircuitBreaker] = {}
_breakers_lock = threading.Lock()


def breaker_for(provider: str) -> CircuitBreaker:
    """Get (or create) the shared breaker for a provider name."""
    with _breakers_lock:
        if provider not in _BREAKERS:
            _BREAKERS[provider] = CircuitBreaker(provider)
        return _BREAKERS[provider]


def reset_all() -> None:
    with _breakers_lock:
        for b in _BREAKERS.values():
            b.reset()


def states() -> dict[str, str]:
    with _breakers_lock:
        return {name: b.state for name, b in _BREAKERS.items()}


if __name__ == "__main__":
    # self-test
    b = CircuitBreaker("test", failure_threshold=3, cooldown_s=1)
    for _ in range(3):
        b.record_failure()
    print("after 3 fails:", b.state, "allow:", b.allow())  # open
    time.sleep(1.2)
    print("after cooldown:", b.state, "allow:", b.allow())  # half_open, allow
    b.record_success()
    print("after success:", b.state, "allow:", b.allow())  # closed
