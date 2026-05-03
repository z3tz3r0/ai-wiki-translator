"""MarkdownDraftStorage · disk-backed DraftStorage adapter.

Layout under ``base_dir``::

    <base_dir>/
        <YYYY-MM-DD>/
            <slug>/
                <slug>.wikitext     # paste-ready translated wikitext
                <slug>.review.md    # source metadata + diff + flags

Idempotent save: re-running for the same ``(date, slug)`` renames the prior
``.wikitext`` / ``.review.md`` to ``.bak`` before overwriting, so the user
keeps one rollback step.
"""

from __future__ import annotations

import asyncio
import datetime
from dataclasses import dataclass
from pathlib import Path

from app.application.dto import DraftMetadata


@dataclass(frozen=True)
class MarkdownDraftStorage:
    """File-system backing for the `DraftStorage` Protocol."""

    base_dir: Path

    @staticmethod
    def default_user_dir() -> Path:
        """``~/Documents/wiki-translations`` · the conventional output location."""
        return Path.home() / "Documents" / "wiki-translations"

    async def save_draft(
        self,
        slug: str,
        wikitext: str,
        review_md: str,
        when: datetime.datetime,
    ) -> Path:
        _validate_slug(slug)
        date_iso = when.date().isoformat()
        out_dir = self.base_dir / date_iso / slug
        await asyncio.to_thread(self._save_sync, out_dir, slug, wikitext, review_md)
        return out_dir

    async def list_drafts(self, since: datetime.datetime | None = None) -> list[DraftMetadata]:
        return await asyncio.to_thread(self._list_sync, since)

    def _save_sync(self, out_dir: Path, slug: str, wikitext: str, review_md: str) -> None:
        out_dir.mkdir(parents=True, exist_ok=True)
        wikitext_path = out_dir / f"{slug}.wikitext"
        review_path = out_dir / f"{slug}.review.md"
        _backup_if_exists(wikitext_path)
        _backup_if_exists(review_path)
        wikitext_path.write_text(wikitext, encoding="utf-8")
        review_path.write_text(review_md, encoding="utf-8")

    def _list_sync(self, since: datetime.datetime | None) -> list[DraftMetadata]:
        if not self.base_dir.exists():
            return []
        cutoff_date = since.date() if since is not None else None
        results: list[DraftMetadata] = []
        for date_dir in self.base_dir.iterdir():
            if not date_dir.is_dir():
                continue
            try:
                when_date = datetime.date.fromisoformat(date_dir.name)
            except ValueError:
                continue
            if cutoff_date is not None and when_date < cutoff_date:
                continue
            for slug_dir in date_dir.iterdir():
                if not slug_dir.is_dir():
                    continue
                results.append(DraftMetadata(slug=slug_dir.name, when=when_date, dir=slug_dir))
        results.sort(key=lambda m: (m.when, m.slug), reverse=True)
        return results


def _validate_slug(slug: str) -> None:
    """Reject slugs that would escape ``<base_dir>/<date>/`` or pollute output.

    Allows non-ASCII letters (Thai, Vietnamese, etc.) and the safe ASCII set.
    Rejects empty strings, path separators, ``..`` traversal, and ASCII
    control characters (which mkdir accepts but break CLI output and any
    downstream string handling).
    """
    if not slug:
        raise ValueError("slug must not be empty")
    if "/" in slug or "\\" in slug:
        raise ValueError(f"slug must not contain path separators: {slug!r}")
    if slug in {".", ".."}:
        raise ValueError(f"slug must not be a path component literal: {slug!r}")
    if any(ord(ch) < 32 for ch in slug):
        raise ValueError(f"slug must not contain control characters: {slug!r}")


def _backup_if_exists(path: Path) -> None:
    if not path.exists():
        return
    backup = path.with_suffix(path.suffix + ".bak")
    if backup.exists():
        backup.unlink()
    path.rename(backup)
