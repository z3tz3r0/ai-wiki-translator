"""GeminiAssistantAdapter · multi-key google-genai async client.

Calls ``client.aio.models.generate_content(...)`` with the section content
plus a system instruction. Three production-readiness wrappers around the
bare SDK call:

* **Multi-key load balancing**: holds N pre-built ``genai.Client`` instances
  (one per API key). Each call picks the least-recently-used key, so N keys
  with 15 RPM each give an effective N x 15 RPM ceiling for sequential
  workloads. Five free-tier keys = 75 effective RPM, which never bottlenecks
  one-article-at-a-time CLI use.
* **Per-key throttle**: caps outgoing requests against any single key at
  ``requests_per_minute`` (default 12 · sits under the 15 RPM free-tier
  ceiling). Only kicks in if even the freshest key would otherwise breach.
* **Single retry on 429 with rotation**: if the chosen key 429s anyway,
  advance to the next key and retry. Respects the server's ``retryDelay``
  hint when parseable; otherwise waits 60 seconds.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from google.genai import types


@dataclass
class GeminiAssistantAdapter:
    """`LLMTranslator` Protocol implementation backed by Google Gemini.

    Construct with one or more ``genai.Client`` instances. Tests typically
    wrap a synthetic client object exposing ``client.aio.models.generate_content``.
    """

    clients: list[Any]
    model: str = "gemini-flash-lite-latest"
    requests_per_minute: int = 12
    max_retries: int = 1
    _last_call_at: list[float] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.clients:
            raise ValueError("`clients` must contain at least one Gemini client")
        self._last_call_at = [0.0] * len(self.clients)

    async def translate_section(self, content: str, system_instruction: str) -> str:
        sleeps_left = self.max_retries
        failed_in_burst: set[int] = set()
        last_exc: Exception | None = None

        while True:
            key_index = self._pick_freshest_key(exclude=failed_in_burst)

            if key_index is None:
                # Every key has 429'd this burst. Sleep on the server's hint and
                # reset so we can try again, if our retry budget permits.
                if sleeps_left <= 0 or last_exc is None:
                    break
                sleeps_left -= 1
                await asyncio.sleep(_retry_delay_seconds(last_exc))
                failed_in_burst.clear()
                continue

            await self._throttle(key_index)
            try:
                config = types.GenerateContentConfig(system_instruction=system_instruction)
                response = await self.clients[key_index].aio.models.generate_content(
                    model=self.model,
                    contents=content,
                    config=config,
                )
                self._last_call_at[key_index] = time.monotonic()
                return response.text or ""
            except Exception as exc:
                last_exc = exc
                self._last_call_at[key_index] = time.monotonic()
                if not _is_retriable(exc):
                    raise
                failed_in_burst.add(key_index)
                # Loop again · the next iteration picks another key, or sleeps if all are exhausted.

        if last_exc is not None:
            raise last_exc
        raise RuntimeError("unreachable")

    def _pick_freshest_key(self, exclude: set[int]) -> int | None:
        """Return the index of the least-recently-used key not in `exclude`."""
        candidates = [i for i in range(len(self.clients)) if i not in exclude]
        if not candidates:
            return None
        return min(candidates, key=lambda i: self._last_call_at[i])

    async def _throttle(self, key_index: int) -> None:
        last_at = self._last_call_at[key_index]
        if last_at == 0.0:
            return
        gap = 60.0 / self.requests_per_minute
        elapsed = time.monotonic() - last_at
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
