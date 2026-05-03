"""Tests for `GeminiAssistantAdapter` · google-genai async client."""

from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any

import pytest

from app.application.ports import LLMTranslator
from app.infrastructure.gemini_genai import GeminiAssistantAdapter


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
    adapter = GeminiAssistantAdapter(client=client)
    assert isinstance(adapter, LLMTranslator)


# --- translate_section -----------------------------------------------------


async def test_translate_section_returns_response_text() -> None:
    client, _ = _make_fake_client(response_text="แปลแล้ว")
    adapter = GeminiAssistantAdapter(client=client)
    out = await adapter.translate_section("source paragraph", "system_instruction")
    assert out == "แปลแล้ว"


async def test_translate_section_passes_content_to_client() -> None:
    client, calls = _make_fake_client()
    adapter = GeminiAssistantAdapter(client=client)
    await adapter.translate_section("paragraph body", "sys")
    assert calls[0]["contents"] == "paragraph body"


async def test_translate_section_passes_system_instruction_via_config() -> None:
    client, calls = _make_fake_client()
    adapter = GeminiAssistantAdapter(client=client)
    await adapter.translate_section("body", "You are a translator.")
    config = calls[0]["config"]
    assert config.system_instruction == "You are a translator."


async def test_translate_section_uses_configured_model() -> None:
    client, calls = _make_fake_client()
    adapter = GeminiAssistantAdapter(client=client, model="gemini-3.0-pro")
    await adapter.translate_section("body", "sys")
    assert calls[0]["model"] == "gemini-3.0-pro"


async def test_translate_section_returns_empty_string_when_response_text_is_none() -> None:
    """Safety blocks or empty completions surface as empty string · caller decides."""
    client, _ = _make_fake_client(response_text=None)
    adapter = GeminiAssistantAdapter(client=client)
    assert await adapter.translate_section("body", "sys") == ""


async def test_translate_section_propagates_client_exception() -> None:
    async def boom(*, model: str, contents: Any, config: Any) -> SimpleNamespace:
        raise RuntimeError("RPC failed")

    client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=boom)))
    adapter = GeminiAssistantAdapter(client=client)
    with pytest.raises(RuntimeError, match="RPC"):
        await adapter.translate_section("body", "sys")


# --- integration -----------------------------------------------------------


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("GEMINI_API_KEY") is None or os.environ.get("CI") is not None,
    reason="set GEMINI_API_KEY and run outside CI for live Gemini integration",
)
async def test_integration_translate_against_live_gemini() -> None:
    from google import genai

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    adapter = GeminiAssistantAdapter(client=client)
    out = await adapter.translate_section(
        "Translate the next sentence to Thai: hello world.",
        "You are a translator from English to Thai. Output Thai only.",
    )
    assert out  # non-empty
