"""Tests for `WikimediaMinTAdapter` · Wikimedia MinT REST adapter."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from app.application.ports import MachineTranslator
from app.infrastructure.wikimedia_mint import WikimediaMinTAdapter

# --- Helpers ---------------------------------------------------------------


def _mint_response(translation: str, source: str = "en", target: str = "th") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "translation": translation,
            "translationtime": 0.25,
            "sourcelanguage": source,
            "targetlanguage": target,
            "model": "nllb200-600M",
        },
    )


def _record_and_respond(
    captured: list[dict[str, Any]],
    response_factory: Callable[[dict[str, Any]], httpx.Response],
) -> httpx.MockTransport:
    """Return a MockTransport that records each request and replies via `response_factory`."""

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else {}
        captured.append(
            {
                "method": request.method,
                "url": str(request.url),
                "headers": dict(request.headers),
                "body": body,
            }
        )
        return response_factory(body)

    return httpx.MockTransport(handler)


# --- Protocol satisfaction --------------------------------------------------


def test_satisfies_machine_translator_protocol() -> None:
    transport = httpx.MockTransport(lambda _: _mint_response("x"))
    adapter = WikimediaMinTAdapter(transport=transport)
    assert isinstance(adapter, MachineTranslator)


# --- translate -------------------------------------------------------------


async def test_translate_returns_translation_field() -> None:
    transport = httpx.MockTransport(lambda _: _mint_response("สวัสดีครับ"))
    adapter = WikimediaMinTAdapter(transport=transport)
    out = await adapter.translate("Hello world", "en", "th")
    assert out == "สวัสดีครับ"


async def test_translate_posts_expected_request_body() -> None:
    captured: list[dict[str, Any]] = []
    transport = _record_and_respond(captured, lambda _: _mint_response("ฟู"))
    adapter = WikimediaMinTAdapter(transport=transport)
    await adapter.translate("Foo", "en", "th")
    assert captured[0]["method"] == "POST"
    assert captured[0]["url"].endswith("/api/translate")
    assert captured[0]["body"] == {
        "format": "text",
        "content": "Foo",
        "source_language": "en",
        "target_language": "th",
    }


async def test_translate_sends_user_agent_header() -> None:
    captured: list[dict[str, Any]] = []
    transport = _record_and_respond(captured, lambda _: _mint_response("x"))
    adapter = WikimediaMinTAdapter(transport=transport, user_agent="custom-ua/1.0 (test)")
    await adapter.translate("Foo", "en", "th")
    assert captured[0]["headers"].get("user-agent") == "custom-ua/1.0 (test)"


async def test_translate_uses_configured_base_url() -> None:
    captured: list[dict[str, Any]] = []
    transport = _record_and_respond(captured, lambda _: _mint_response("x"))
    adapter = WikimediaMinTAdapter(transport=transport, base_url="https://example.test")
    await adapter.translate("Foo", "en", "th")
    assert captured[0]["url"].startswith("https://example.test")


async def test_translate_handles_non_string_translation_field() -> None:
    """Defensive: if the server ever returns a malformed body, return empty string."""

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"translation": None, "translationtime": 0.0})

    adapter = WikimediaMinTAdapter(transport=httpx.MockTransport(handler))
    assert await adapter.translate("Foo", "en", "th") == ""


async def test_translate_raises_on_http_error() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(500, json={"detail": "boom"}))
    adapter = WikimediaMinTAdapter(transport=transport)
    with pytest.raises(httpx.HTTPStatusError):
        await adapter.translate("Foo", "en", "th")


# --- translate_batch -------------------------------------------------------


async def test_translate_batch_empty_returns_empty() -> None:
    transport = httpx.MockTransport(lambda _: pytest.fail("should not be called"))
    adapter = WikimediaMinTAdapter(transport=transport)
    assert await adapter.translate_batch([], "en", "th") == []


async def test_translate_batch_returns_results_in_order() -> None:
    """Each input maps to its own translation; order matches input order."""

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        return _mint_response(f"<{body['content']}>")

    adapter = WikimediaMinTAdapter(transport=httpx.MockTransport(handler))
    out = await adapter.translate_batch(["Foo", "Bar", "Baz"], "en", "th")
    assert out == ["<Foo>", "<Bar>", "<Baz>"]


async def test_translate_batch_caps_concurrency() -> None:
    """`max_concurrency=2` must serialize so at most 2 requests are in flight at once."""
    in_flight = 0
    peak = 0
    lock = asyncio.Lock()

    async def slow_handler(request: httpx.Request) -> httpx.Response:
        nonlocal in_flight, peak
        async with lock:
            in_flight += 1
            peak = max(peak, in_flight)
        await asyncio.sleep(0.01)
        async with lock:
            in_flight -= 1
        body = json.loads(request.content)
        return _mint_response(body["content"])

    transport = httpx.MockTransport(slow_handler)
    adapter = WikimediaMinTAdapter(transport=transport, max_concurrency=2)
    await adapter.translate_batch(["a", "b", "c", "d", "e"], "en", "th")
    assert peak <= 2, f"peak in-flight requests = {peak}, expected <= 2"


# --- integration -----------------------------------------------------------


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("CI") is not None,
    reason="hits live translate.wmcloud.org · skip on CI",
)
async def test_integration_against_live_mint() -> None:
    adapter = WikimediaMinTAdapter()
    out = await adapter.translate("Hello world", "en", "th")
    assert out  # MinT may return varying Thai forms; just check non-empty
