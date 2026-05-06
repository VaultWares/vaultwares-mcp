from __future__ import annotations

import time
from dataclasses import dataclass
from threading import Lock


@dataclass
class TokenBucketSnapshot:
    capacity: int
    tokens: float
    refill_per_sec: float
    reset_in_s: float


class TokenBucket:
    def __init__(self, capacity: int, refill_per_sec: float) -> None:
        self._capacity = int(capacity)
        self._refill_per_sec = float(refill_per_sec)
        self._tokens = float(capacity)
        self._last = time.monotonic()
        self._lock = Lock()

    def take(self, amount: int = 1) -> bool:
        amount = int(amount)
        if amount <= 0:
            return True
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last
            self._last = now
            self._tokens = min(self._capacity, self._tokens + elapsed * self._refill_per_sec)
            if self._tokens >= amount:
                self._tokens -= amount
                return True
            return False

    def snapshot(self) -> TokenBucketSnapshot:
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last
            tokens = min(self._capacity, self._tokens + elapsed * self._refill_per_sec)
            missing = max(0.0, 1.0 - tokens)
            reset_in_s = missing / self._refill_per_sec if self._refill_per_sec > 0 else 0.0
            return TokenBucketSnapshot(
                capacity=self._capacity,
                tokens=tokens,
                refill_per_sec=self._refill_per_sec,
                reset_in_s=reset_in_s,
            )

