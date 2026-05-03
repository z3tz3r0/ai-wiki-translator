"""FilePromptRepository · loads prompt templates from a directory."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FilePromptRepository:
    """Reads ``<prompts_dir>/<template_id>.md`` as the system instruction body.

    ``template_id`` is validated at the boundary: no path separators, no
    ``.``/``..`` literals, no traversal.
    """

    prompts_dir: Path

    async def load(self, template_id: str) -> str:
        _validate_template_id(template_id)
        path = self.prompts_dir / f"{template_id}.md"
        return await asyncio.to_thread(path.read_text, encoding="utf-8")


def _validate_template_id(template_id: str) -> None:
    if not template_id:
        raise ValueError("template_id must not be empty")
    if "/" in template_id or "\\" in template_id:
        raise ValueError(f"template_id must not contain path separators: {template_id!r}")
    if template_id in {".", ".."}:
        raise ValueError(f"template_id must not be a path component literal: {template_id!r}")
    if any(ord(ch) < 32 for ch in template_id):
        raise ValueError(f"template_id must not contain control characters: {template_id!r}")
