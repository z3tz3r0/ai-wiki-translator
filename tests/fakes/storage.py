"""In-memory InMemoryDraftStorage for Phase 2 contract tests."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.application.dto import DraftMetadata


class InMemoryDraftStorage:
    """Tracks drafts in a dict keyed by (date, slug); returns synthetic Paths.

    Structurally satisfies `app.application.ports.DraftStorage`.
    No disk I/O · the returned Path is `Path('/inmemory') / <date>.iso / <slug>`.
    """

    def __init__(self) -> None:
        self._drafts: dict[tuple[str, str], tuple[str, str, datetime]] = {}

    async def save_draft(
        self,
        slug: str,
        wikitext: str,
        review_md: str,
        when: datetime,
    ) -> Path:
        key = (when.date().isoformat(), slug)
        self._drafts[key] = (wikitext, review_md, when)
        return Path("/inmemory") / when.date().isoformat() / slug

    async def list_drafts(self, since: datetime | None = None) -> list[DraftMetadata]:
        results: list[DraftMetadata] = []
        for (date_iso, slug), (_, _, when) in self._drafts.items():
            if since is not None and when < since:
                continue
            results.append(
                DraftMetadata(
                    slug=slug,
                    when=when.date(),
                    dir=Path("/inmemory") / date_iso / slug,
                )
            )
        results.sort(key=lambda m: (m.when, m.slug), reverse=True)
        return results
