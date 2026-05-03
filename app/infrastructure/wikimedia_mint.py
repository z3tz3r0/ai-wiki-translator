"""WikimediaMinTAdapter · free machine translation via Wikimedia's MinT service.

POSTs to ``https://translate.wmcloud.org/api/translate`` per the live OpenAPI
spec (``GET /openapi.json``):

* request: ``{"format": "text", "content": str, "source_language": str,
  "target_language": str}`` (model optional · server picks NLLB-200 by default
  for most pairs)
* response: ``{"translation": str, "translationtime": float, ...}``

No auth. Wikimedia policy expects a descriptive ``User-Agent`` header.

MinT exposes no native batch endpoint; ``translate_batch`` fans out via
``asyncio.gather`` under a small semaphore so we don't slam the service when
processing an article's worth of wikilinks at once.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx

DEFAULT_USER_AGENT = "ai-wiki-translator/0.1 (https://github.com/z3tz3r0/ai-wiki-translator)"
DEFAULT_BASE_URL = "https://translate.wmcloud.org"


@dataclass(frozen=True)
class WikimediaMinTAdapter:
    """`MachineTranslator` Protocol implementation backed by Wikimedia MinT.

    Inject an ``httpx.MockTransport`` as ``transport`` to short-circuit the
    network in unit tests; live runs leave it ``None`` so httpx picks the
    default async transport.
    """

    transport: httpx.AsyncBaseTransport | None = None
    user_agent: str = DEFAULT_USER_AGENT
    timeout: float = 30.0
    base_url: str = DEFAULT_BASE_URL
    max_concurrency: int = 5

    async def translate(self, text: str, src: str, tgt: str) -> str:
        async with self._client() as client:
            return await self._post_translate(client, text, src, tgt)

    async def translate_batch(self, texts: list[str], src: str, tgt: str) -> list[str]:
        if not texts:
            return []
        sem = asyncio.Semaphore(self.max_concurrency)

        async with self._client() as client:

            async def bounded(text: str) -> str:
                async with sem:
                    return await self._post_translate(client, text, src, tgt)

            return await asyncio.gather(*(bounded(t) for t in texts))

    async def _post_translate(
        self, client: httpx.AsyncClient, text: str, src: str, tgt: str
    ) -> str:
        response = await client.post(
            "/api/translate",
            json={
                "format": "text",
                "content": text,
                "source_language": src,
                "target_language": tgt,
            },
        )
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        translation = payload.get("translation", "")
        return translation if isinstance(translation, str) else ""

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            headers={"User-Agent": self.user_agent, "Accept": "application/json"},
            transport=self.transport,
            timeout=self.timeout,
        )
