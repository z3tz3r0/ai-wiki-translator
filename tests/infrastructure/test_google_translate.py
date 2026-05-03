"""Tests for `GoogleTranslateAdapter` · sync google-cloud-translate via asyncio.to_thread."""

from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any

import pytest

from app.application.ports import MachineTranslator
from app.infrastructure.google_translate import GoogleTranslateAdapter


class FakeTranslateClient:
    """Synthetic client mirroring `TranslationServiceClient.translate_text`."""

    def __init__(self, mapping: dict[str, str] | None = None) -> None:
        self.mapping = mapping or {}
        self.calls: list[dict[str, Any]] = []

    def translate_text(self, request: dict[str, Any]) -> SimpleNamespace:
        self.calls.append(request)
        translations = []
        for content in request["contents"]:
            translated = self.mapping.get(content, f"<<tr:{content}>>")
            translations.append(SimpleNamespace(translated_text=translated))
        return SimpleNamespace(translations=translations)


def _make_adapter(client: FakeTranslateClient) -> GoogleTranslateAdapter:
    return GoogleTranslateAdapter(client=client, project_id="proj-123")


def test_satisfies_machine_translator_protocol() -> None:
    adapter = _make_adapter(FakeTranslateClient())
    assert isinstance(adapter, MachineTranslator)


# --- translate --------------------------------------------------------------


async def test_translate_single_text_returns_translation() -> None:
    client = FakeTranslateClient(mapping={"hello": "สวัสดี"})
    adapter = _make_adapter(client)
    out = await adapter.translate("hello", "en", "th")
    assert out == "สวัสดี"


async def test_translate_passes_languages_to_client() -> None:
    client = FakeTranslateClient()
    adapter = _make_adapter(client)
    await adapter.translate("hello", "en", "th")
    request = client.calls[0]
    assert request["source_language_code"] == "en"
    assert request["target_language_code"] == "th"


async def test_translate_request_includes_project_parent_and_mime() -> None:
    client = FakeTranslateClient()
    adapter = GoogleTranslateAdapter(client=client, project_id="proj-456")
    await adapter.translate("hello", "en", "th")
    request = client.calls[0]
    assert request["parent"] == "projects/proj-456/locations/global"
    assert request["mime_type"] == "text/plain"


# --- translate_batch -------------------------------------------------------


async def test_translate_batch_returns_one_result_per_input() -> None:
    client = FakeTranslateClient(mapping={"a": "เอ", "b": "บี", "c": "ซี"})
    adapter = _make_adapter(client)
    out = await adapter.translate_batch(["a", "b", "c"], "en", "th")
    assert out == ["เอ", "บี", "ซี"]


async def test_translate_batch_empty_input_returns_empty_without_calling_client() -> None:
    client = FakeTranslateClient()
    adapter = _make_adapter(client)
    out = await adapter.translate_batch([], "en", "th")
    assert out == []
    assert client.calls == []


async def test_translate_batch_sends_one_request() -> None:
    """Batch sends a single API call · cost-efficient."""
    client = FakeTranslateClient()
    adapter = _make_adapter(client)
    await adapter.translate_batch(["a", "b", "c"], "en", "th")
    assert len(client.calls) == 1
    assert client.calls[0]["contents"] == ["a", "b", "c"]


# --- error handling --------------------------------------------------------


async def test_translate_propagates_client_exception() -> None:
    class BoomClient:
        def translate_text(self, request: dict[str, Any]) -> SimpleNamespace:
            raise RuntimeError("API quota exceeded")

    adapter = GoogleTranslateAdapter(client=BoomClient(), project_id="p")
    with pytest.raises(RuntimeError, match="quota"):
        await adapter.translate("hello", "en", "th")


# --- integration -----------------------------------------------------------


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("GOOGLE_TRANSLATE_PROJECT_ID") is None or os.environ.get("CI") is not None,
    reason="set GOOGLE_TRANSLATE_PROJECT_ID + GOOGLE_APPLICATION_CREDENTIALS, run outside CI",
)
async def test_integration_translate_against_live_google() -> None:
    from google.cloud import translate_v3

    client = translate_v3.TranslationServiceClient()
    adapter = GoogleTranslateAdapter(
        client=client,
        project_id=os.environ["GOOGLE_TRANSLATE_PROJECT_ID"],
    )
    out = await adapter.translate("hello world", "en", "th")
    assert out  # any non-empty Thai translation
