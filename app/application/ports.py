"""Application-layer ports as runtime-checkable Protocols."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Protocol, runtime_checkable

from app.application.dto import DraftMetadata
from app.domain.entities import Article
from app.domain.values import Glossary


@runtime_checkable
class WikipediaReader(Protocol):
    """Read-only access to MediaWiki API across language wikis."""

    async def fetch_article(self, title: str, lang: str) -> Article | None: ...

    async def fetch_langlinks(self, title: str, lang: str) -> dict[str, str]: ...


@runtime_checkable
class WikidataReader(Protocol):
    """Read-only access to Wikidata · Q-ID resolution and claims."""

    async def resolve_qid(self, title: str, lang: str) -> str | None: ...

    async def fetch_claims(self, qid: str) -> dict[str, list[str]]: ...


@runtime_checkable
class MachineTranslator(Protocol):
    """Deterministic translator · for IMAGE / QUOTE / BULLET / structural sections."""

    async def translate(self, text: str, src: str, tgt: str) -> str: ...

    async def translate_batch(self, texts: list[str], src: str, tgt: str) -> list[str]: ...


@runtime_checkable
class LLMTranslator(Protocol):
    """LLM-backed translator · for TEXT sections needing nuance."""

    async def translate_section(self, content: str, system_instruction: str) -> str: ...


@runtime_checkable
class PromptTemplateRepository(Protocol):
    """Loads system-instruction prompt templates by id."""

    async def load(self, template_id: str) -> str: ...


@runtime_checkable
class GlossaryRepository(Protocol):
    """Loads a glossary file (term:translation pairs)."""

    async def load(self, path: str | None) -> Glossary: ...


@runtime_checkable
class DraftStorage(Protocol):
    """Persists translation drafts to a review-friendly file layout.

    `datetime` parameters here are NAIVE UTC by convention. Phase 4's real
    adapter must enforce that at the boundary; passing a tz-aware value will
    raise on comparison with stored entries.

    `save_draft` MUST have upsert semantics · saving the same `(when.date(),
    slug)` twice overwrites the prior draft. Phase 4's `MarkdownDraftStorage`
    should write a `.bak` of the previous run before overwriting on disk.
    """

    async def save_draft(
        self,
        slug: str,
        wikitext: str,
        review_md: str,
        when: datetime,
    ) -> Path: ...

    async def list_drafts(self, since: datetime | None = None) -> list[DraftMetadata]: ...
