"""GeminiAssistantAdapter · section translation through google-genai.

Calls ``client.aio.models.generate_content(...)`` with the section content
plus a system instruction. Key rotation, per-key throttling, rests after
429s and dropping of unusable keys live in ``GeminiKeyPool``
(``gemini_key_pool.py``), which this adapter can share with the
transliteration validator.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from google.genai import types

from app.infrastructure.gemini_key_pool import DEFAULT_GEMINI_MODEL, GeminiKeyPool


@dataclass
class GeminiAssistantAdapter:
    """`LLMTranslator` Protocol implementation backed by Google Gemini.

    ``pool`` holds the keys, throttle and retry settings, and is meant to be
    shared with every other Gemini adapter in the process.
    """

    pool: GeminiKeyPool
    model: str = DEFAULT_GEMINI_MODEL

    async def translate_section(self, content: str, system_instruction: str) -> str:
        config = types.GenerateContentConfig(system_instruction=system_instruction)

        async def request(client: Any) -> str:
            response = await client.aio.models.generate_content(
                model=self.model, contents=content, config=config
            )
            return response.text or ""

        return await self.pool.run(request)
