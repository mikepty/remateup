"""FASE 11 — Rate limiter for AI providers.

Respects provider limits with a sliding window, configurable timeout per
call and exponential backoff with retries.
"""

import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as _FutureTimeoutError
from typing import Any, Callable, Optional


class RateLimitError(Exception):
    pass


class RateLimiter:
    def __init__(
        self,
        max_calls_per_minute: int = 60,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
        backoff_base: float = 1.0,
        backoff_factor: float = 2.0,
        backoff_max: float = 30.0,
    ):
        self.max_calls_per_minute = max_calls_per_minute
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.backoff_factor = backoff_factor
        self.backoff_max = backoff_max
        self._calls: deque[float] = deque()
        self._lock = threading.Lock()
        self._stats = {"calls": 0, "errors": 0, "retries": 0}

    def acquire(self):
        with self._lock:
            now = time.monotonic()
            while self._calls and now - self._calls[0] > 60.0:
                self._calls.popleft()
            if len(self._calls) >= self.max_calls_per_minute:
                wait = 60.0 - (now - self._calls[0])
                if wait > 0:
                    time.sleep(wait)
                now = time.monotonic()
                while self._calls and now - self._calls[0] > 60.0:
                    self._calls.popleft()
            self._calls.append(now)
            self._stats["calls"] += 1

    def _call_with_timeout(self, fn: Callable[[], Any]) -> Any:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(fn)
            try:
                return future.result(timeout=self.timeout_seconds)
            except _FutureTimeoutError:
                future.cancel()
                raise TimeoutError(
                    f"Call exceeded timeout of {self.timeout_seconds}s"
                ) from None

    def execute(self, fn: Callable[[], Any]) -> tuple[Any, int]:
        attempts = 0
        while True:
            self.acquire()
            attempts += 1
            try:
                return self._call_with_timeout(fn), attempts
            except TimeoutError as e:
                self._stats["errors"] += 1
                if attempts > self.max_retries:
                    raise RateLimitError(str(e))
                self._stats["retries"] += 1
                self._sleep_backoff(attempts)
            except Exception as e:
                self._stats["errors"] += 1
                if attempts > self.max_retries:
                    raise
                self._stats["retries"] += 1
                self._sleep_backoff(attempts)

    def _sleep_backoff(self, attempt: int):
        delay = min(self.backoff_base * (self.backoff_factor ** (attempt - 1)), self.backoff_max)
        time.sleep(delay)

    def reset(self):
        with self._lock:
            self._calls.clear()
            self._stats = {"calls": 0, "errors": 0, "retries": 0}

    def stats(self) -> dict:
        with self._lock:
            return dict(self._stats)
