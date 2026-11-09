"""Tests for `GeminiKeyPool` · shared key rotation for every Gemini adapter.

Errors are real ``google.genai.errors`` objects built from the response body
Gemini returns (shape recorded in google-gemini/gemini-cli#8437), so the
parsing runs against what the SDK actually raises. Time is faked: no test
waits on the wall clock.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest
from google.genai import errors

from app.application.dto import LanguageRuleSet, TransliterationCandidate
from app.infrastructure.gemini_genai import DEFAULT_GEMINI_MODEL, GeminiAssistantAdapter
from app.infrastructure.gemini_key_pool import (
    GeminiKeyPool,
    retry_delay_seconds,
    seconds_until_pacific_midnight,
)
from app.infrastructure.lite_validator import LiteValidatorAdapter

PER_MINUTE = "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"
PER_DAY = "GenerateRequestsPerDayPerProjectPerModel-FreeTier"
# 2026-11-09 03:00 PST · next Pacific midnight is 21 hours away.
BASE_UTC = datetime.datetime(2026, 11, 9, 11, 0, tzinfo=datetime.UTC)
HOURS_21 = 21 * 3600.0


# --- error factories (real SDK classes, real body shape) --------------------


def _error(code: int, status: str, details: list[dict[str, Any]] | None = None) -> errors.APIError:
    body: dict[str, Any] = {"error": {"code": code, "message": "m", "status": status}}
    if details is not None:
        body["error"]["details"] = details
    cls = errors.ServerError if code >= 500 else errors.ClientError
    return cls(code, body)


def rate_limited(quota_id: str = PER_MINUTE, delay: str = "41s") -> errors.APIError:
    return _error(
        429,
        "RESOURCE_EXHAUSTED",
        [
            {
                "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                "violations": [
                    {
                        "quotaMetric": "generativelanguage.googleapis.com/"
                        "generate_content_free_tier_requests",
                        "quotaId": quota_id,
                    }
                ],
            },
            {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": delay},
        ],
    )


def invalid_key() -> errors.APIError:
    return _error(
        400,
        "INVALID_ARGUMENT",
        [{"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": "API_KEY_INVALID"}],
    )


def forbidden() -> errors.APIError:
    return _error(403, "PERMISSION_DENIED")


def bad_request() -> errors.APIError:
    return _error(400, "INVALID_ARGUMENT")


# --- fakes -------------------------------------------------------------------


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


@dataclass
class FakeKey:
    """One key's client · raises queued failures first, then succeeds."""

    label: str
    log: list[str]
    failures: list[Exception] = field(default_factory=list)

    async def call(self) -> str:
        self.log.append(self.label)
        await asyncio.sleep(0)  # yield so gathered calls really overlap
        if self.failures:
            raise self.failures.pop(0)
        return f"ok-{self.label}"


def _pool(ft: FakeTime, *keys: FakeKey) -> GeminiKeyPool:
    return GeminiKeyPool(clients=list(keys), clock=ft.clock, now_utc=ft.utc, sleep=ft.sleep)


async def _call(pool: GeminiKeyPool) -> str:
    return await pool.run(lambda client: client.call())


# --- rotation ------------------------------------------------------------------


def test_empty_clients_raises() -> None:
    with pytest.raises(ValueError, match="at least one"):
        GeminiKeyPool(clients=[])


async def test_parallel_calls_spread_across_keys() -> None:
    """Self-consistency fires samples together · each must get its own key."""
    log: list[str] = []
    ft = FakeTime()
    pool = _pool(ft, FakeKey("a", log), FakeKey("b", log), FakeKey("c", log))

    await asyncio.gather(_call(pool), _call(pool), _call(pool))

    assert sorted(log) == ["a", "b", "c"]


async def test_per_minute_429_rests_key_for_retry_delay_across_calls() -> None:
    log: list[str] = []
    ft = FakeTime()
    pool = _pool(ft, FakeKey("a", log, [rate_limited(PER_MINUTE, "41s")]), FakeKey("b", log))

    assert await _call(pool) == "ok-b"
    ft.now += 10  # a still resting
    assert await _call(pool) == "ok-b"
    ft.now += 40  # a's 41s rest is over
    assert await _call(pool) == "ok-a"
    assert log == ["a", "b", "b", "a"]


async def test_per_day_429_rests_key_until_pacific_midnight() -> None:
    """A per-day 429 carries a short retryDelay too · the quotaId must win."""
    log: list[str] = []
    ft = FakeTime()
    pool = _pool(ft, FakeKey("a", log, [rate_limited(PER_DAY, "41s")]), FakeKey("b", log))

    assert await _call(pool) == "ok-b"
    ft.now += HOURS_21 - 60  # one minute before the reset
    assert await _call(pool) == "ok-b"
    ft.now += 120  # one minute after the reset
    assert await _call(pool) == "ok-a"
    assert log == ["a", "b", "b", "a"]


@pytest.mark.parametrize("make_error", [invalid_key, forbidden], ids=["400-key-invalid", "403"])
async def test_unusable_key_is_dropped_for_the_run(make_error: Any) -> None:
    log: list[str] = []
    ft = FakeTime()
    pool = _pool(ft, FakeKey("a", log, [make_error()]), FakeKey("b", log))

    assert await _call(pool) == "ok-b"
    ft.now += 2 * 86400.0
    assert await _call(pool) == "ok-b"
    assert log == ["a", "b", "b"]


async def test_bad_request_raises_and_keeps_the_key() -> None:
    """A 400 about the request itself is not the key's fault."""
    log: list[str] = []
    ft = FakeTime()
    pool = _pool(ft, FakeKey("a", log, [bad_request()]))

    with pytest.raises(errors.ClientError):
        await _call(pool)
    ft.now += 10
    assert await _call(pool) == "ok-a"


async def test_all_keys_briefly_resting_waits_for_the_soonest() -> None:
    log: list[str] = []
    ft = FakeTime()
    pool = _pool(
        ft,
        FakeKey("a", log, [rate_limited(PER_MINUTE, "30s")]),
        FakeKey("b", log, [rate_limited(PER_MINUTE, "10s")]),
    )

    assert await _call(pool) == "ok-b"
    assert ft.slept == [10.0]


async def test_all_keys_resting_for_the_day_raises_without_sleeping() -> None:
    log: list[str] = []
    ft = FakeTime()
    pool = _pool(
        ft,
        FakeKey("a", log, [rate_limited(PER_DAY)]),
        FakeKey("b", log, [rate_limited(PER_DAY)]),
    )

    with pytest.raises(errors.ClientError) as caught:
        await _call(pool)
    assert caught.value.code == 429
    assert ft.slept == []


async def test_rest_is_logged_with_key_number_and_counts(caplog: pytest.LogCaptureFixture) -> None:
    log: list[str] = []
    ft = FakeTime()
    pool = _pool(ft, FakeKey("a", log, [rate_limited(PER_MINUTE, "41s")]), FakeKey("b", log))

    with caplog.at_level(logging.WARNING, logger="app.infrastructure.gemini_key_pool"):
        await _call(pool)

    text = caplog.text
    assert "key #1" in text
    assert "1 ready, 1 resting, 0 dropped" in text


# --- pure helpers --------------------------------------------------------------


def test_retry_delay_reads_sdk_shaped_error() -> None:
    """The SDK stores the whole body in `details` · the hint is nested under error.details."""
    assert retry_delay_seconds(rate_limited(PER_MINUTE, "41s")) == 41.0


def test_seconds_until_pacific_midnight_plain_day() -> None:
    assert seconds_until_pacific_midnight(BASE_UTC) == HOURS_21


def test_seconds_until_pacific_midnight_on_dst_end_day() -> None:
    """2026-11-01 01:00 PDT · clocks fall back at 02:00, so midnight is 24 real hours away."""
    now = datetime.datetime(2026, 11, 1, 8, 0, tzinfo=datetime.UTC)
    assert seconds_until_pacific_midnight(now) == 24 * 3600.0


# --- adapters on one shared pool -------------------------------------------------


def _genai_key(label: str, log: list[str], failures: list[Exception] | None = None) -> Any:
    """`genai.Client`-shaped fake · records label and model per call."""
    queued = list(failures or [])

    async def generate_content(*, model: str, contents: Any, config: Any) -> SimpleNamespace:
        log.append(f"{label}:{model}")
        if queued:
            raise queued.pop(0)
        return SimpleNamespace(text="[]")

    return SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    )


def _rules() -> LanguageRuleSet:
    return LanguageRuleSet(
        lang="en",
        title="rules-en",
        url="https://th.wikipedia.org/wiki/rules-en",
        scraped_at=datetime.datetime(2026, 5, 4, 12, 0, 0),
        entries=(),
        excerpt="",
    )


async def test_adapters_share_one_pool_and_default_to_pinned_model() -> None:
    log: list[str] = []
    ft = FakeTime()
    pool = GeminiKeyPool(
        clients=[_genai_key("a", log, [rate_limited(PER_DAY)]), _genai_key("b", log)],
        clock=ft.clock,
        now_utc=ft.utc,
        sleep=ft.sleep,
    )
    translator = GeminiAssistantAdapter(pool=pool)
    validator = LiteValidatorAdapter(pool=pool, judge_template="judge")

    await translator.translate_section("body", "sys")
    ft.now += 60
    await validator.validate((TransliterationCandidate(thai="ก", context="c"),), _rules())

    model = DEFAULT_GEMINI_MODEL
    assert model == "gemini-flash-lite-latest"
    assert log == [f"a:{model}", f"b:{model}", f"b:{model}"]


async def test_validator_returns_uncertain_when_every_key_rests_for_the_day() -> None:
    log: list[str] = []
    ft = FakeTime()
    pool = GeminiKeyPool(
        clients=[_genai_key("a", log, [rate_limited(PER_DAY)])],
        clock=ft.clock,
        now_utc=ft.utc,
        sleep=ft.sleep,
    )
    with pytest.raises(errors.ClientError):
        await GeminiAssistantAdapter(pool=pool).translate_section("body", "sys")

    out = await LiteValidatorAdapter(pool=pool, judge_template="judge").validate(
        (TransliterationCandidate(thai="ก", context="c"),), _rules()
    )

    assert out[0].status == "uncertain"
    assert "validator call failed" in out[0].reason
    assert len(log) == 1  # the validator never spent a request


def test_adapter_rejects_both_clients_and_pool() -> None:
    pool = GeminiKeyPool(clients=[object()])
    with pytest.raises(ValueError, match="not both"):
        GeminiAssistantAdapter(clients=[object()], pool=pool)
