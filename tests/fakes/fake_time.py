"""Fake time for `GeminiKeyPool` tests · no test waits on the wall clock."""

from __future__ import annotations

import datetime
from typing import Any

from app.infrastructure.gemini_key_pool import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_REQUESTS_PER_MINUTE,
    GeminiKeyPool,
)

# 2026-11-09 03:00 PST · next Pacific midnight is 21 hours away.
BASE_UTC = datetime.datetime(2026, 11, 9, 11, 0, tzinfo=datetime.UTC)


class FakeTime:
    """Monotonic clock, UTC clock and sleep that move together."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.slept: list[float] = []

    def clock(self) -> float:
        return self.now

    def utc(self) -> datetime.datetime:
        return BASE_UTC + datetime.timedelta(seconds=self.now - 1000.0)

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def fake_pool(
    *clients: Any,
    ft: FakeTime | None = None,
    requests_per_minute: int = DEFAULT_REQUESTS_PER_MINUTE,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> GeminiKeyPool:
    """A `GeminiKeyPool` on fake time · pass ``ft`` to read what it slept."""
    time = ft or FakeTime()
    return GeminiKeyPool(
        clients=list(clients),
        requests_per_minute=requests_per_minute,
        max_retries=max_retries,
        clock=time.clock,
        now_utc=time.utc,
        sleep=time.sleep,
    )
