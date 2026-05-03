"""GeminiAssistantAdapter · google-genai async client with free-tier throttling.

Calls ``client.aio.models.generate_content(...)`` with the section content
plus a system instruction. Two production-readiness wrappers around the bare
SDK call:

* **Ahead-of-time throttle**: caps outgoing requests at ``requests_per_minute``
  (default 12, which sits under Gemini's free-tier 15 RPM ceiling with
  headroom). Sequential per-section calls in a long article would otherwise
  fire faster than the ceiling and 429 mid-run.
* **Single retry on 429**: respects the server's ``retryDelay`` hint when
  parseable, falls back to a 60-second wait. Avoids losing an article's
  worth of in-flight translation to a transient burst.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from google.genai import types


@dataclass
class GeminiAssistantAdapter:
    """`LLMTranslator` Protocol implementation backed by Google Gemini."""

    client: Any
    model: str = "gemini-flash-lite-latest"
    requests_per_minute: int = 12
    max_retries: int = 1
    _last_call_at: float = field(default=0.0, init=False, repr=False)

    async def translate_section(self, content: str, system_instruction: str) -> str:
        await self._throttle()
        for attempt in range(self.max_retries + 1):
            try:
                config = types.GenerateContentConfig(system_instruction=system_instruction)
                response = await self.client.aio.models.generate_content(
                    model=self.model,
                    contents=content,
                    config=config,
                )
                self._last_call_at = time.monotonic()
                return response.text or ""
            except Exception as exc:
                if attempt < self.max_retries and _is_retriable(exc):
                    await asyncio.sleep(_retry_delay_seconds(exc))
                    continue
                raise
        raise RuntimeError("unreachable")

    async def _throttle(self) -> None:
        if self._last_call_at == 0.0:
            return
        gap = 60.0 / self.requests_per_minute
        elapsed = time.monotonic() - self._last_call_at
        if elapsed < gap:
            await asyncio.sleep(gap - elapsed)


def _is_retriable(exc: Exception) -> bool:
    return getattr(exc, "code", None) == 429


def _retry_delay_seconds(exc: Exception) -> float:
    """Best-effort parse of ``retryDelay`` from google-genai's error details."""
    details = getattr(exc, "details", None) or []
    if not isinstance(details, list):
        return 60.0
    for d in details:
        if not isinstance(d, dict):
            continue
        if not str(d.get("@type", "")).endswith("RetryInfo"):
            continue
        raw = d.get("retryDelay", "60s")
        if isinstance(raw, str) and raw.endswith("s"):
            try:
                return float(raw[:-1])
            except ValueError:
                pass
    return 60.0
