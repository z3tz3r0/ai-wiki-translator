"""GeminiAssistantAdapter · section translation through google-genai.

Calls ``client.aio.models.generate_content(...)`` with the section content
plus a system instruction. Key rotation, per-key throttling, rests after
429s and dropping of unusable keys live in ``GeminiKeyPool``
(``gemini_key_pool.py``), which this adapter can share with the
transliteration validator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from google.genai import types

from app.infrastructure.gemini_key_pool import GeminiKeyPool, resolve_pool

# Google's alias · moves to each new Flash-Lite release (2 weeks' notice by
# email). Override with WIKI_TRANSLATOR_GEMINI_MODEL to pin a version.
DEFAULT_GEMINI_MODEL = "gemini-flash-lite-latest"


@dataclass
class GeminiAssistantAdapter:
    """`LLMTranslator` Protocol implementation backed by Google Gemini.

    Pass a shared ``pool``, or ``clients`` (one ``genai.Client`` per key) to
    build a private pool with ``requests_per_minute`` and ``max_retries``.
    """

    clients: list[Any] = field(default_factory=list)
    model: str = DEFAULT_GEMINI_MODEL
    requests_per_minute: int = 12
    max_retries: int = 1
    pool: GeminiKeyPool | None = None
    _pool: GeminiKeyPool = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._pool = resolve_pool(
            self.clients,
            self.pool,
            requests_per_minute=self.requests_per_minute,
            max_retries=self.max_retries,
        )

    async def translate_section(self, content: str, system_instruction: str) -> str:
        config = types.GenerateContentConfig(system_instruction=system_instruction)

        async def request(client: Any) -> str:
            response = await client.aio.models.generate_content(
                model=self.model, contents=content, config=config
            )
            return response.text or ""

        return await self._pool.run(request)
