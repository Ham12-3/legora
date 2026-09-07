"""Client-side rate budgets.

Requests-per-minute and tokens-per-minute are tracked separately because
document extraction hits TPM long before RPM. Both are sliding one-minute
windows; ``acquire`` waits until the request fits.
"""

import asyncio
import time
from collections import deque


class _Window:
    def __init__(self, budget: int) -> None:
        self.budget = budget
        self._events: deque[tuple[float, int]] = deque()
        self._used = 0

    def _expire(self, now: float) -> None:
        while self._events and now - self._events[0][0] >= 60.0:
            _, amount = self._events.popleft()
            self._used -= amount

    def wait_time(self, amount: int, now: float) -> float:
        self._expire(now)
        if self._used + amount <= self.budget or not self._events:
            return 0.0
        oldest_ts, _ = self._events[0]
        return max(0.0, 60.0 - (now - oldest_ts))

    def spend(self, amount: int, now: float) -> None:
        self._events.append((now, amount))
        self._used += amount


class RateLimiter:
    def __init__(self, *, rpm: int, tpm: int, max_concurrency: int) -> None:
        self._rpm = _Window(rpm)
        self._tpm = _Window(tpm)
        self._lock = asyncio.Lock()
        self.semaphore = asyncio.Semaphore(max_concurrency)

    async def acquire(self, estimated_tokens: int) -> None:
        """Block until one request of ``estimated_tokens`` fits both budgets."""
        while True:
            async with self._lock:
                now = time.monotonic()
                wait = max(self._rpm.wait_time(1, now), self._tpm.wait_time(estimated_tokens, now))
                if wait <= 0:
                    self._rpm.spend(1, now)
                    self._tpm.spend(estimated_tokens, now)
                    return
            await asyncio.sleep(min(wait, 5.0))

    def record_actual(self, actual_tokens: int, estimated_tokens: int) -> None:
        """Correct the TPM window once the provider reports real usage."""
        delta = actual_tokens - estimated_tokens
        if delta > 0:
            self._tpm.spend(delta, time.monotonic())
