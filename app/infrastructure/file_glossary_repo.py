"""FileGlossaryRepository · reads `term:translation` lines into a Glossary."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from app.domain.text_transforms import parse_glossary_lines
from app.domain.values import Glossary


@dataclass(frozen=True)
class FileGlossaryRepository:
    """Reads a glossary file via the domain `parse_glossary_lines` helper.

    ``path=None`` is treated as "no glossary" and returns an empty mapping.
    """

    async def load(self, path: str | None) -> Glossary:
        if path is None:
            return {}
        text = await asyncio.to_thread(Path(path).read_text, encoding="utf-8")
        return parse_glossary_lines(text.splitlines())
