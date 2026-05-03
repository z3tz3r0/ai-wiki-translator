"""RunQueuedTranslationsUseCase · iterate a TOML-defined queue of titles."""

from __future__ import annotations

import tomllib
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from app.application.dto import Draft, TranslateArticleCommand
from app.application.use_cases.translate_article import TranslateArticleUseCase


def parse_queue_toml(toml_text: str) -> list[TranslateArticleCommand]:
    """Parse a TOML queue body into translate commands.

    Schema:
        [[entry]]
        title = "..."          # required, str
        source_lang = "..."    # optional, str · maps to source_lang_override
        glossary = "..."       # optional, str · maps to glossary_path
    """
    if not toml_text.strip():
        return []
    try:
        data: dict[str, Any] = tomllib.loads(toml_text)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"invalid TOML in queue: {exc}") from exc
    raw_entries: list[dict[str, Any]] = data.get("entry", [])
    commands: list[TranslateArticleCommand] = []
    for entry in raw_entries:
        if "title" not in entry:
            raise KeyError("queue entry missing required 'title' field")
        title = entry["title"]
        if not isinstance(title, str):
            raise TypeError(f"queue entry 'title' must be a string, got {type(title).__name__}")
        source_lang = entry.get("source_lang")
        if source_lang is not None and not isinstance(source_lang, str):
            raise TypeError(
                f"queue entry 'source_lang' must be a string, got {type(source_lang).__name__}"
            )
        glossary = entry.get("glossary")
        if glossary is not None and not isinstance(glossary, str):
            raise TypeError(
                f"queue entry 'glossary' must be a string, got {type(glossary).__name__}"
            )
        commands.append(
            TranslateArticleCommand(
                title=title,
                source_lang_override=source_lang,
                glossary_path=glossary,
            )
        )
    return commands


@dataclass(frozen=True)
class RunQueuedTranslationsUseCase:
    translate: TranslateArticleUseCase

    async def execute(self, commands: Iterable[TranslateArticleCommand]) -> list[Draft]:
        results: list[Draft] = []
        for cmd in commands:
            results.append(await self.translate.execute(cmd))
        return results
