"""GoogleTranslateAdapter · async wrapper over google-cloud-translate v3.

The upstream client is sync, so calls run on a thread via
``asyncio.to_thread`` to avoid blocking the event loop.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GoogleTranslateAdapter:
    """`MachineTranslator` Protocol implementation backed by Google Cloud Translate v3.

    Inject ``google.cloud.translate_v3.TranslationServiceClient`` as ``client``;
    tests inject a synthetic class with a compatible ``translate_text`` shape.
    """

    client: Any
    project_id: str
    location: str = "global"
    mime_type: str = "text/plain"

    async def translate(self, text: str, src: str, tgt: str) -> str:
        results = await self.translate_batch([text], src, tgt)
        return results[0]

    async def translate_batch(self, texts: list[str], src: str, tgt: str) -> list[str]:
        if not texts:
            return []
        request = {
            "parent": f"projects/{self.project_id}/locations/{self.location}",
            "contents": list(texts),
            "mime_type": self.mime_type,
            "source_language_code": src,
            "target_language_code": tgt,
        }
        response = await asyncio.to_thread(self.client.translate_text, request)
        return [t.translated_text for t in response.translations]
