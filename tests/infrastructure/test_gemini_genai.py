"""Tests for `GeminiAssistantAdapter` · google-genai async client."""

from __future__ import annotations

import os
import time
from types import SimpleNamespace
from typing import Any, ClassVar

import pytest

from app.application.ports import LLMTranslator
from app.infrastructure.gemini_genai import GeminiAssistantAdapter, _retry_delay_seconds


def _make_fake_client(
    response_text: str | None = "translated text",
) -> tuple[Any, list[dict[str, Any]]]:
    """Return a `(fake_client, calls)` pair mimicking `genai.Client.aio.models`.

    `calls` records each invocation so tests can assert what was sent.
    """
    calls: list[dict[str, Any]] = []

    async def generate_content(*, model: str, contents: Any, config: Any) -> SimpleNamespace:
        calls.append({"model": model, "contents": contents, "config": config})
        return SimpleNamespace(text=response_text)

    client = SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    )
    return client, calls


def test_satisfies_llm_translator_protocol() -> None:
    client, _ = _make_fake_client()
    adapter = GeminiAssistantAdapter(clients=[client])
    assert isinstance(adapter, LLMTranslator)


# --- translate_section -----------------------------------------------------


async def test_translate_section_returns_response_text() -> None:
    client, _ = _make_fake_client(response_text="แปลแล้ว")
    adapter = GeminiAssistantAdapter(clients=[client])
    out = await adapter.translate_section("source paragraph", "system_instruction")
    assert out == "แปลแล้ว"


async def test_translate_section_passes_content_to_client() -> None:
    client, calls = _make_fake_client()
    adapter = GeminiAssistantAdapter(clients=[client])
    await adapter.translate_section("paragraph body", "sys")
    assert calls[0]["contents"] == "paragraph body"


async def test_translate_section_passes_system_instruction_via_config() -> None:
    client, calls = _make_fake_client()
    adapter = GeminiAssistantAdapter(clients=[client])
    await adapter.translate_section("body", "You are a translator.")
    config = calls[0]["config"]
    assert config.system_instruction == "You are a translator."


async def test_translate_section_uses_configured_model() -> None:
    client, calls = _make_fake_client()
    adapter = GeminiAssistantAdapter(clients=[client], model="gemini-3.0-pro")
    await adapter.translate_section("body", "sys")
    assert calls[0]["model"] == "gemini-3.0-pro"


async def test_translate_section_returns_empty_string_when_response_text_is_none() -> None:
    """Safety blocks or empty completions surface as empty string · caller decides."""
    client, _ = _make_fake_client(response_text=None)
    adapter = GeminiAssistantAdapter(clients=[client])
    assert await adapter.translate_section("body", "sys") == ""


async def test_translate_section_propagates_client_exception() -> None:
    async def boom(*, model: str, contents: Any, config: Any) -> SimpleNamespace:
        raise RuntimeError("RPC failed")

    client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=boom)))
    adapter = GeminiAssistantAdapter(clients=[client])
    with pytest.raises(RuntimeError, match="RPC"):
        await adapter.translate_section("body", "sys")


# --- throttling and retry --------------------------------------------------


async def test_translate_section_throttles_consecutive_calls() -> None:
    """Second call must wait so the effective rate stays under `requests_per_minute`."""
    client, _ = _make_fake_client()
    # 60 RPM = 1s spacing · keeps the test snappy while still asserting the wait happens
    adapter = GeminiAssistantAdapter(clients=[client], requests_per_minute=60)

    start = time.monotonic()
    await adapter.translate_section("a", "sys")
    await adapter.translate_section("b", "sys")
    elapsed = time.monotonic() - start
    # First call has no wait; second call waits ~1s. Lower bound 0.9 to allow scheduler jitter.
    assert elapsed >= 0.9, f"second call did not throttle · elapsed={elapsed:.3f}s"


async def test_translate_section_retries_once_on_429() -> None:
    """A 429 with `code` attribute triggers one retry · second attempt succeeds."""
    calls: list[int] = []

    class RateLimit(Exception):
        code: ClassVar[int] = 429
        details: ClassVar[list[dict[str, Any]]] = [
            {
                "@type": "type.googleapis.com/google.rpc.RetryInfo",
                "retryDelay": "0s",
            }
        ]

    async def flaky(*, model: str, contents: Any, config: Any) -> SimpleNamespace:
        calls.append(1)
        if len(calls) == 1:
            raise RateLimit("rate limit")
        return SimpleNamespace(text="recovered")

    client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=flaky)))
    adapter = GeminiAssistantAdapter(clients=[client])
    out = await adapter.translate_section("body", "sys")
    assert out == "recovered"
    assert len(calls) == 2


async def test_translate_section_does_not_retry_non_429_errors() -> None:
    """Non-retriable exceptions raise immediately without retrying."""
    calls: list[int] = []

    async def boom(*, model: str, contents: Any, config: Any) -> SimpleNamespace:
        calls.append(1)
        raise RuntimeError("non-rate-limit failure")

    client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=boom)))
    adapter = GeminiAssistantAdapter(clients=[client])
    with pytest.raises(RuntimeError, match="non-rate-limit"):
        await adapter.translate_section("body", "sys")
    assert len(calls) == 1


async def test_translate_section_retries_once_on_503() -> None:
    """A 503 with `code` attribute triggers one retry · second attempt succeeds."""
    calls: list[int] = []

    class Unavailable(Exception):
        code: ClassVar[int] = 503

    async def flaky(*, model: str, contents: Any, config: Any) -> SimpleNamespace:
        calls.append(1)
        if len(calls) == 1:
            raise Unavailable("model overloaded")
        return SimpleNamespace(text="recovered")

    client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=flaky)))
    adapter = GeminiAssistantAdapter(clients=[client])
    out = await adapter.translate_section("body", "sys")
    assert out == "recovered"
    assert len(calls) == 2


async def test_translate_section_reraises_503_after_retries_exhausted() -> None:
    """If every attempt hits 503, the last exception is propagated."""

    class Unavailable(Exception):
        code: ClassVar[int] = 503

    async def always_503(*, model: str, contents: Any, config: Any) -> SimpleNamespace:
        raise Unavailable("model overloaded")

    client = SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=always_503))
    )
    adapter = GeminiAssistantAdapter(clients=[client], max_retries=1)
    with pytest.raises(Unavailable):
        await adapter.translate_section("body", "sys")


async def test_translate_section_reraises_after_retries_exhausted() -> None:
    """If every retry hits 429, the last exception is propagated."""

    class RateLimit(Exception):
        code: ClassVar[int] = 429
        details: ClassVar[list[dict[str, Any]]] = [
            {
                "@type": "type.googleapis.com/google.rpc.RetryInfo",
                "retryDelay": "0s",
            }
        ]

    async def always_429(*, model: str, contents: Any, config: Any) -> SimpleNamespace:
        raise RateLimit("rate limit")

    client = SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=always_429))
    )
    adapter = GeminiAssistantAdapter(clients=[client], max_retries=1)
    with pytest.raises(RateLimit):
        await adapter.translate_section("body", "sys")


# --- multi-key rotation ----------------------------------------------------


def test_empty_clients_list_raises() -> None:
    with pytest.raises(ValueError, match="at least one"):
        GeminiAssistantAdapter(clients=[])


async def test_multi_key_load_balances_via_least_recently_used() -> None:
    """Sequential calls rotate across keys before reusing any single one."""
    used: list[str] = []

    def make_marked_client(label: str) -> Any:
        async def generate_content(*, model: str, contents: Any, config: Any) -> SimpleNamespace:
            used.append(label)
            return SimpleNamespace(text="ok")

        return SimpleNamespace(
            aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
        )

    a = make_marked_client("a")
    b = make_marked_client("b")
    c = make_marked_client("c")
    adapter = GeminiAssistantAdapter(clients=[a, b, c])

    for _ in range(3):
        await adapter.translate_section("body", "sys")

    # Each key must be used once before any is reused.
    assert sorted(used) == ["a", "b", "c"], f"keys not rotated: {used}"


async def test_multi_key_429_fails_over_to_next_key() -> None:
    """When the picked key 429s, the same call retries on a different key."""
    used: list[str] = []

    class RateLimit(Exception):
        code: ClassVar[int] = 429
        details: ClassVar[list[dict[str, Any]]] = [
            {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "0s"},
        ]

    def make_client(label: str, *, rate_limit: bool) -> Any:
        async def generate_content(*, model: str, contents: Any, config: Any) -> SimpleNamespace:
            used.append(label)
            if rate_limit:
                raise RateLimit(f"{label} rate-limited")
            return SimpleNamespace(text=f"from-{label}")

        return SimpleNamespace(
            aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
        )

    rate_limited = make_client("a", rate_limit=True)
    healthy = make_client("b", rate_limit=False)
    adapter = GeminiAssistantAdapter(clients=[rate_limited, healthy])

    out = await adapter.translate_section("body", "sys")
    assert out == "from-b"
    assert used == ["a", "b"]  # tried a first, fell over to b


async def test_multi_key_all_429_then_succeeds_after_sleep() -> None:
    """If all keys 429 in a burst, one sleep + retry must recover."""
    used: list[tuple[str, int]] = []  # (label, attempt_number_for_that_label)
    counter: dict[str, int] = {"a": 0, "b": 0}

    class RateLimit(Exception):
        code: ClassVar[int] = 429
        details: ClassVar[list[dict[str, Any]]] = [
            {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "0s"},
        ]

    def make_client(label: str) -> Any:
        async def generate_content(*, model: str, contents: Any, config: Any) -> SimpleNamespace:
            counter[label] += 1
            used.append((label, counter[label]))
            if counter[label] == 1:
                raise RateLimit(f"{label} rate-limited")
            return SimpleNamespace(text=f"from-{label}")

        return SimpleNamespace(
            aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
        )

    adapter = GeminiAssistantAdapter(clients=[make_client("a"), make_client("b")], max_retries=1)
    out = await adapter.translate_section("body", "sys")
    assert out.startswith("from-")
    # Two failed attempts (one per key) + one successful retry
    assert len(used) >= 3


def test_retry_delay_seconds_parses_retry_info() -> None:
    """Pulls the `retryDelay` field from RetryInfo details, drops the trailing 's'."""

    class RateLimit(Exception):
        details: ClassVar[list[dict[str, Any]]] = [
            {"@type": "type.googleapis.com/google.rpc.QuotaFailure"},
            {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "31s"},
        ]

    assert _retry_delay_seconds(RateLimit()) == 31.0


def test_retry_delay_seconds_falls_back_to_60_when_missing() -> None:
    """Defaults to 60s when no RetryInfo is present or details are malformed."""
    assert _retry_delay_seconds(RuntimeError("plain")) == 60.0

    class WithMalformed(Exception):
        details = "not a list"

    assert _retry_delay_seconds(WithMalformed()) == 60.0


def test_retry_delay_seconds_uses_exponential_backoff_for_503() -> None:
    """503 has no server-supplied delay · use 2^attempt capped at 30s."""

    class Unavailable(Exception):
        code: ClassVar[int] = 503

    exc = Unavailable()
    assert _retry_delay_seconds(exc, attempt=0) == 1.0
    assert _retry_delay_seconds(exc, attempt=1) == 2.0
    assert _retry_delay_seconds(exc, attempt=2) == 4.0
    # Cap kicks in
    assert _retry_delay_seconds(exc, attempt=10) == 30.0


# --- integration -----------------------------------------------------------


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("GEMINI_API_KEY") is None or os.environ.get("CI") is not None,
    reason="set GEMINI_API_KEY and run outside CI for live Gemini integration",
)
async def test_integration_translate_against_live_gemini() -> None:
    from google import genai

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    adapter = GeminiAssistantAdapter(clients=[client])
    out = await adapter.translate_section(
        "Translate the next sentence to Thai: hello world.",
        "You are a translator from English to Thai. Output Thai only.",
    )
    assert out  # non-empty
