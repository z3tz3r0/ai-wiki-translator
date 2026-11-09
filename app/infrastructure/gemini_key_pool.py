"""GeminiKeyPool · one key rotation shared by every Gemini adapter.

Free-tier Gemini quota is counted per Google Cloud project, not per key
(https://ai.google.dev/gemini-api/docs/rate-limits), so extra keys add
capacity only when each comes from its own project. The pool treats every
key as its own quota bucket and remembers each key's state across calls:

* **Reservation**: a key is claimed the moment it is picked, so calls fired
  together (self-consistency samples) land on different keys. Each key is
  spaced to ``requests_per_minute``. A call that waited for its slot checks
  the key again before sending, and a cancelled wait gives the slot back.
* **Per-minute 429**: the key rests for the server's ``retryDelay`` hint.
* **Per-day 429** (a ``quotaId`` containing ``PerDay``): the key rests until
  the next midnight Pacific time, when Google resets daily quota. These
  errors also carry a short ``retryDelay``, so the quotaId decides. A later,
  shorter rest never cuts a longer one short.
* **Unusable key** (401, 403, or 400 with an ``API_KEY_*`` reason): the key
  is dropped for the rest of the process.
* **503**: the model is overloaded for everyone, so the call backs off
  exponentially before any key tries again. The key is not penalised.

When no key can serve, the error raised explains why: a quota error while
any key is resting, a key error only when every key is dropped. Every state
change logs the key's 1-based position among the configured keys and the
pool counts. Key values are never logged.
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
from typing import Any, NamedTuple
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# Google's alias · moves to each new Flash-Lite release (2 weeks' notice by
# email). Override with WIKI_TRANSLATOR_GEMINI_MODEL to pin a version.
DEFAULT_GEMINI_MODEL = "gemini-flash-lite-latest"
DEFAULT_REQUESTS_PER_MINUTE = 12
DEFAULT_MAX_RETRIES = 1
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


class _Slot(NamedTuple):
    """A reserved send time on one key."""

    key: int
    wait: float
    booked_until: float
    previous: float


@dataclass
class _CallState:
    """What one ``run`` call has seen so far."""

    retries_left: int
    tried: set[int] = field(default_factory=set)
    last_exc: Exception | None = None
    last_quota_exc: Exception | None = None


def _utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _monotonic() -> float:
    return time.monotonic()


async def _sleep(seconds: float) -> None:
    # Looked up at call time so tests can monkeypatch asyncio.sleep.
    await asyncio.sleep(seconds)


@dataclass
class GeminiKeyPool:
    """Rotates ``genai.Client`` instances (one per key) and tracks each key's state."""

    clients: list[Any]
    requests_per_minute: int = DEFAULT_REQUESTS_PER_MINUTE
    max_retries: int = DEFAULT_MAX_RETRIES
    clock: Callable[[], float] = _monotonic
    now_utc: Callable[[], datetime.datetime] = _utc_now
    sleep: Callable[[float], Awaitable[None]] = _sleep
    _next_free_at: list[float] = field(default_factory=list, init=False, repr=False)
    _rest_until: list[float] = field(default_factory=list, init=False, repr=False)
    _dropped: set[int] = field(default_factory=set, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.clients:
            raise ValueError("`clients` must contain at least one Gemini client")
        if self.requests_per_minute <= 0:
            raise ValueError("`requests_per_minute` must be positive")
        if self.max_retries < 0:
            raise ValueError("`max_retries` must be zero or more")
        self._next_free_at = [-math.inf] * len(self.clients)
        self._rest_until = [-math.inf] * len(self.clients)

    async def run[T](self, request: Callable[[Any], Awaitable[T]]) -> T:
        """Run ``request(client)`` on the best available key, rotating on key failures.

        Each key is tried at most once per round. When no key is free, the call
        waits for the soonest one (up to ``max_retries`` rounds) or raises the
        error that explains why waiting cannot help.
        """
        state = _CallState(retries_left=self.max_retries)
        while True:
            slot = self._acquire(exclude=state.tried)
            if slot is None:
                await self._wait_for_round(state)
                continue
            if slot.wait > 0:
                await self._wait_for_slot(slot)
                if not self._usable(slot.key, self.clock()):
                    continue  # dropped or put to rest while this call waited
            try:
                return await request(self.clients[slot.key])
            except Exception as exc:
                await self._handle_failure(slot.key, exc, state)

    def counts(self) -> tuple[int, int, int]:
        """Return ``(ready, resting, dropped)`` key counts right now."""
        now = self.clock()
        total = len(self.clients)
        dropped = len(self._dropped)
        resting = sum(
            1 for i in range(total) if i not in self._dropped and self._rest_until[i] > now
        )
        return total - dropped - resting, resting, dropped

    def _usable(self, index: int, now: float) -> bool:
        return index not in self._dropped and self._rest_until[index] <= now

    def _acquire(self, exclude: set[int]) -> _Slot | None:
        """Claim the usable key that frees up first."""
        now = self.clock()
        usable = [i for i in range(len(self.clients)) if i not in exclude and self._usable(i, now)]
        if not usable:
            return None
        index = min(usable, key=lambda i: self._next_free_at[i])
        previous = self._next_free_at[index]
        start = max(now, previous)
        booked_until = start + 60.0 / self.requests_per_minute
        self._next_free_at[index] = booked_until
        return _Slot(index, start - now, booked_until, previous)

    async def _wait_for_slot(self, slot: _Slot) -> None:
        """Sleep until the reserved send time · give the slot back if cancelled meanwhile."""
        logger.debug("key #%d · call starts in %.1fs", slot.key + 1, slot.wait)
        try:
            await self.sleep(slot.wait)
        except asyncio.CancelledError:
            # Only when nothing was booked after this slot · otherwise it stays used.
            if self._next_free_at[slot.key] == slot.booked_until:
                self._next_free_at[slot.key] = slot.previous
            raise

    async def _wait_for_round(self, state: _CallState) -> None:
        """No untried key is free · wait for the soonest one, or raise when that cannot help."""
        wait = self._retry_wait()
        if state.retries_left <= 0 or wait is None:
            raise self._give_up(state)
        self._log_retry(wait, state.retries_left)
        state.retries_left -= 1
        state.tried.clear()
        await self.sleep(wait)

    async def _handle_failure(self, index: int, exc: Exception, state: _CallState) -> None:
        kind = classify(exc)
        if kind is FailureKind.FATAL:
            raise exc
        state.last_exc = exc
        if kind is FailureKind.OVERLOAD:
            await self._back_off(exc, state)
            return
        if kind is not FailureKind.BAD_KEY:
            state.last_quota_exc = exc
        state.tried.add(index)
        self._penalize(index, kind, exc)

    async def _back_off(self, exc: Exception, state: _CallState) -> None:
        """503 · the model is busy for every key, so wait before any key tries again."""
        if state.retries_left <= 0:
            raise exc
        attempt = self.max_retries - state.retries_left
        delay = retry_delay_seconds(exc, attempt=attempt)
        logger.warning(
            "model overloaded (HTTP 503) · backing off %.1fs before retry %d/%d",
            delay,
            attempt + 1,
            self.max_retries,
        )
        state.retries_left -= 1
        await self.sleep(delay)

    def _retry_wait(self) -> float | None:
        """Seconds until a resting key is back, or None when waiting cannot help."""
        alive = [i for i in range(len(self.clients)) if i not in self._dropped]
        if not alive:
            return None
        ready_in = max(0.0, min(self._rest_until[i] for i in alive) - self.clock())
        return None if ready_in > MAX_RETRY_WAIT_SECONDS else ready_in

    def _give_up(self, state: _CallState) -> Exception:
        """The error that explains why no key can serve, whatever order keys failed in."""
        if state.last_exc is not None and is_quota_exhaustion(state.last_exc):
            return state.last_exc
        if self.counts()[1] > 0:  # some key is resting · quota is the blocker
            return state.last_quota_exc or self._exhausted()
        return state.last_exc or self._exhausted()

    def _penalize(self, index: int, kind: FailureKind, exc: Exception) -> None:
        if kind is FailureKind.BAD_KEY:
            self._dropped.add(index)
            action = "dropped for this run"
        elif kind is FailureKind.PER_DAY:
            remaining = self._rest(index, seconds_until_pacific_midnight(self.now_utc()))
            action = f"resting {_format_rest(remaining)} until midnight Pacific"
        else:
            remaining = self._rest(index, retry_delay_seconds(exc))
            action = f"resting {_format_rest(remaining)}"
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

    def _rest(self, index: int, seconds: float) -> float:
        """Rest a key for ``seconds``, keeping any longer rest · returns seconds left."""
        now = self.clock()
        self._rest_until[index] = max(self._rest_until[index], now + seconds)
        return self._rest_until[index] - now

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
    requests_per_minute: int | None,
    max_retries: int | None,
) -> GeminiKeyPool:
    """Adapter helper · use the shared ``pool``, or build a private one from ``clients``."""
    if pool is not None and clients:
        raise ValueError("pass `clients` or a shared `pool`, not both")
    if pool is not None:
        if requests_per_minute is not None or max_retries is not None:
            raise ValueError(
                "set `requests_per_minute` and `max_retries` on the shared pool, not the adapter"
            )
        return pool
    return GeminiKeyPool(
        clients=clients,
        requests_per_minute=(
            DEFAULT_REQUESTS_PER_MINUTE if requests_per_minute is None else requests_per_minute
        ),
        max_retries=DEFAULT_MAX_RETRIES if max_retries is None else max_retries,
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


def _format_rest(seconds: float) -> str:
    return f"{seconds / 3600:.1f}h" if seconds >= 3600 else f"{seconds:.0f}s"


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
