"""GeminiKeyPool · one key rotation shared by every Gemini adapter.

Free-tier Gemini quota is counted per Google Cloud project, not per key
(https://ai.google.dev/gemini-api/docs/rate-limits), so extra keys add
capacity only when each comes from its own project. The pool treats every
key as its own quota bucket and remembers each key's state across calls:

* **Reservation**: a key is claimed the moment it is picked, so calls fired
  together (self-consistency samples) land on different keys. Each key is
  spaced to ``requests_per_minute``.
* **Per-minute 429**: the key rests for the server's ``retryDelay`` hint.
* **Per-day 429** (a ``quotaId`` containing ``PerDay``): the key rests until
  the next midnight Pacific time, when Google resets daily quota. These
  errors also carry a short ``retryDelay``, so the quotaId decides.
* **Unusable key** (401, 403, or 400 with an ``API_KEY_*`` reason): the key
  is dropped for the rest of the process.
* **503**: the model is overloaded for everyone. The call moves to another
  key without penalising this one, then backs off exponentially.

Every state change logs the key's 1-based position in ``GEMINI_API_KEYS``
and the pool counts. Key values are never logged.
"""

from __future__ import annotations

import asyncio
import datetime
import enum
import functools
import logging
import math
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

DEFAULT_RETRY_DELAY_SECONDS = 60.0
MAX_OVERLOAD_BACKOFF_SECONDS = 30.0
# Longest wait for a resting key before a call gives up · per-minute hints
# stay under this, per-day rests never do.
MAX_RETRY_WAIT_SECONDS = 120.0
_BAD_KEY_CODES = frozenset({401, 403})
_BAD_KEY_REASONS = frozenset({"API_KEY_INVALID", "API_KEY_SERVICE_BLOCKED"})


class FailureKind(enum.Enum):
    PER_DAY = "per-day quota"
    PER_MINUTE = "per-minute quota"
    OVERLOAD = "model overloaded"
    BAD_KEY = "unusable key"
    FATAL = "not a key problem"


class KeyPoolExhaustedError(RuntimeError):
    """No key can serve a call, and the call has no error of its own to re-raise."""

    def __init__(self, message: str, *, quota: bool) -> None:
        super().__init__(message)
        self.quota = quota  # True when keys are resting, False when all are dropped


def _utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


@dataclass
class GeminiKeyPool:
    """Rotates ``genai.Client`` instances (one per key) and tracks each key's state."""

    clients: list[Any]
    requests_per_minute: int = 12
    max_retries: int = 1
    clock: Callable[[], float] = time.monotonic
    now_utc: Callable[[], datetime.datetime] = _utc_now
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    _next_free_at: list[float] = field(default_factory=list, init=False, repr=False)
    _rest_until: list[float] = field(default_factory=list, init=False, repr=False)
    _dropped: set[int] = field(default_factory=set, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.clients:
            raise ValueError("`clients` must contain at least one Gemini client")
        self._next_free_at = [-math.inf] * len(self.clients)
        self._rest_until = [-math.inf] * len(self.clients)

    async def run[T](self, request: Callable[[Any], Awaitable[T]]) -> T:
        """Run ``request(client)`` on the best available key, rotating on key failures.

        Each key is tried at most once per round. When no key is free, the call
        waits for the soonest one (up to ``max_retries`` rounds) or re-raises
        the last key error when waiting cannot help.
        """
        tried: set[int] = set()
        retries_left = self.max_retries
        last_exc: Exception | None = None
        while True:
            slot = self._acquire(exclude=tried)
            if slot is None:
                wait = self._retry_wait(last_exc, attempt=self.max_retries - retries_left)
                if retries_left <= 0 or wait is None:
                    raise last_exc or self._exhausted()
                self._log_retry(wait, retries_left)
                retries_left -= 1
                tried.clear()
                await self.sleep(wait)
                continue
            index, wait = slot
            logger.debug("key #%d · call starts in %.1fs", index + 1, wait)
            if wait > 0:
                await self.sleep(wait)
            try:
                return await request(self.clients[index])
            except Exception as exc:
                kind = classify(exc)
                if kind is FailureKind.FATAL:
                    raise
                last_exc = exc
                tried.add(index)
                self._penalize(index, kind, exc)

    def counts(self) -> tuple[int, int, int]:
        """Return ``(ready, resting, dropped)`` key counts right now."""
        now = self.clock()
        total = len(self.clients)
        dropped = len(self._dropped)
        resting = sum(
            1 for i in range(total) if i not in self._dropped and self._rest_until[i] > now
        )
        return total - dropped - resting, resting, dropped

    def _acquire(self, exclude: set[int]) -> tuple[int, float] | None:
        """Claim the usable key that frees up first · returns ``(index, seconds to wait)``."""
        now = self.clock()
        usable = [
            i
            for i in range(len(self.clients))
            if i not in exclude and i not in self._dropped and self._rest_until[i] <= now
        ]
        if not usable:
            return None
        index = min(usable, key=lambda i: self._next_free_at[i])
        start = max(now, self._next_free_at[index])
        self._next_free_at[index] = start + 60.0 / self.requests_per_minute
        return index, start - now

    def _retry_wait(self, last_exc: Exception | None, attempt: int) -> float | None:
        """Seconds until a retry round can start, or None when waiting cannot help."""
        alive = [i for i in range(len(self.clients)) if i not in self._dropped]
        if not alive:
            return None
        ready_in = max(0.0, min(self._rest_until[i] for i in alive) - self.clock())
        if ready_in > MAX_RETRY_WAIT_SECONDS:
            return None
        if last_exc is not None and classify(last_exc) is FailureKind.OVERLOAD:
            return max(ready_in, retry_delay_seconds(last_exc, attempt=attempt))
        return ready_in

    def _penalize(self, index: int, kind: FailureKind, exc: Exception) -> None:
        if kind is FailureKind.OVERLOAD:
            logger.info("key #%d: %s · trying another key", index + 1, kind.value)
            return
        if kind is FailureKind.BAD_KEY:
            self._dropped.add(index)
            action = "dropped for this run"
        elif kind is FailureKind.PER_DAY:
            rest = seconds_until_pacific_midnight(self.now_utc())
            self._rest_until[index] = self.clock() + rest
            action = f"resting {rest / 3600:.1f}h until midnight Pacific"
        else:
            rest = retry_delay_seconds(exc)
            self._rest_until[index] = self.clock() + rest
            action = f"resting {rest:.0f}s"
        ready, resting, dropped = self.counts()
        logger.warning(
            "key #%d %s (%s, HTTP %s) · pool: %d ready, %d resting, %d dropped",
            index + 1,
            action,
            kind.value,
            getattr(exc, "code", "?"),
            ready,
            resting,
            dropped,
        )

    def _log_retry(self, wait: float, retries_left: int) -> None:
        ready, resting, dropped = self.counts()
        logger.warning(
            "no key free · waiting %.1fs before retry %d/%d · pool: %d ready, %d resting, "
            "%d dropped",
            wait,
            self.max_retries - retries_left + 1,
            self.max_retries,
            ready,
            resting,
            dropped,
        )

    def _exhausted(self) -> KeyPoolExhaustedError:
        ready, resting, dropped = self.counts()
        return KeyPoolExhaustedError(
            f"no usable Gemini key · {ready} ready, {resting} resting, {dropped} dropped",
            quota=resting > 0,
        )


def resolve_pool(
    clients: list[Any],
    pool: GeminiKeyPool | None,
    *,
    requests_per_minute: int,
    max_retries: int,
) -> GeminiKeyPool:
    """Adapter helper · use the shared ``pool``, or build a private one from ``clients``."""
    if pool is not None and clients:
        raise ValueError("pass `clients` or a shared `pool`, not both")
    if pool is not None:
        return pool
    return GeminiKeyPool(
        clients=clients, requests_per_minute=requests_per_minute, max_retries=max_retries
    )


def classify(exc: BaseException) -> FailureKind:
    """Decide what a failed call says about the key that made it."""
    code = getattr(exc, "code", None)
    if code == 429:
        return FailureKind.PER_DAY if _is_per_day(exc) else FailureKind.PER_MINUTE
    if code == 503:
        return FailureKind.OVERLOAD
    if code in _BAD_KEY_CODES or (code == 400 and _error_reason(exc) in _BAD_KEY_REASONS):
        return FailureKind.BAD_KEY
    return FailureKind.FATAL


def is_quota_exhaustion(exc: BaseException) -> bool:
    """True when a call failed only because quota or model capacity ran out."""
    if isinstance(exc, KeyPoolExhaustedError):
        return exc.quota
    return classify(exc) in (FailureKind.PER_DAY, FailureKind.PER_MINUTE, FailureKind.OVERLOAD)


def retry_delay_seconds(exc: BaseException, attempt: int = 0) -> float:
    """Seconds to rest after ``exc``.

    * 503: exponential backoff ``min(2 ** attempt, 30s)`` · the server gives no hint.
    * 429: the server's ``RetryInfo.retryDelay`` (e.g. ``"41s"``), else 60s.
    """
    if getattr(exc, "code", None) == 503:
        return min(2.0**attempt, MAX_OVERLOAD_BACKOFF_SECONDS)
    for detail in _error_details(exc):
        if str(detail.get("@type", "")).endswith("RetryInfo"):
            parsed = _parse_duration(detail.get("retryDelay"))
            if parsed is not None:
                return parsed
    return DEFAULT_RETRY_DELAY_SECONDS


def seconds_until_pacific_midnight(now_utc: datetime.datetime) -> float:
    """Real seconds until the next 00:00 Pacific time, correct across DST changes."""
    pacific = _pacific()
    local = now_utc.astimezone(pacific)
    midnight = datetime.datetime.combine(
        local.date() + datetime.timedelta(days=1), datetime.time(0), tzinfo=pacific
    )
    # Subtract in UTC · same-tzinfo subtraction ignores the DST offset change.
    return (midnight.astimezone(datetime.UTC) - now_utc.astimezone(datetime.UTC)).total_seconds()


@functools.cache
def _pacific() -> ZoneInfo:
    # Loaded on first use · Windows needs the `tzdata` package for this zone.
    return ZoneInfo("America/Los_Angeles")


def _error_details(exc: BaseException) -> list[dict[str, Any]]:
    """Detail dicts from an error.

    ``google.genai.errors.APIError`` stores the whole response body in
    ``details`` (``{"error": {"details": [...]}}``). A bare list is accepted too.
    """
    raw = getattr(exc, "details", None)
    if isinstance(raw, dict):
        error = raw.get("error")
        raw = error.get("details") if isinstance(error, dict) else None
    if not isinstance(raw, list):
        return []
    return [d for d in raw if isinstance(d, dict)]


def _quota_ids(exc: BaseException) -> list[str]:
    ids: list[str] = []
    for detail in _error_details(exc):
        if str(detail.get("@type", "")).endswith("QuotaFailure"):
            violations = detail.get("violations") or []
            ids.extend(str(v.get("quotaId", "")) for v in violations if isinstance(v, dict))
    return ids


def _is_per_day(exc: BaseException) -> bool:
    return any("PerDay" in quota_id for quota_id in _quota_ids(exc))


def _error_reason(exc: BaseException) -> str:
    for detail in _error_details(exc):
        if str(detail.get("@type", "")).endswith("ErrorInfo"):
            return str(detail.get("reason", ""))
    return ""


def _parse_duration(raw: object) -> float | None:
    """Parse a protobuf JSON duration like ``"41s"`` or ``"0.5s"``."""
    if not isinstance(raw, str) or not raw.endswith("s"):
        return None
    try:
        value = float(raw[:-1])
    except ValueError:
        return None
    return value if math.isfinite(value) and value >= 0 else None
