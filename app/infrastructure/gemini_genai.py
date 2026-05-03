"""GeminiAssistantAdapter · google-genai async client.

Calls ``client.aio.models.generate_content(...)`` with the section content
plus a system instruction. Stateless per request; the caller composes
prompt-cache wiring in a future phase.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from google.genai import types


@dataclass(frozen=True)
class GeminiAssistantAdapter:
    """`LLMTranslator` Protocol implementation backed by Google Gemini.

    Inject ``google.genai.Client`` as ``client``; tests inject a synthetic
    object exposing ``client.aio.models.generate_content``.
    """

    client: Any
    model: str = "gemini-2.0-flash"

    async def translate_section(self, content: str, system_instruction: str) -> str:
        config = types.GenerateContentConfig(system_instruction=system_instruction)
        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=content,
            config=config,
        )
        return response.text or ""
