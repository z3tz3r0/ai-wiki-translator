"""Tests for `ListDraftsUseCase`."""

from __future__ import annotations

import datetime

from app.application.dto import DraftMetadata
from app.application.use_cases.list_drafts import ListDraftsUseCase
from tests.fakes.storage import InMemoryDraftStorage


async def test_list_drafts_empty_storage_returns_empty() -> None:
    uc = ListDraftsUseCase(storage=InMemoryDraftStorage())
    assert await uc.execute() == []


async def test_list_drafts_returns_drafts_in_date_descending_order() -> None:
    storage = InMemoryDraftStorage()
    await storage.save_draft("old", "w", "r", datetime.datetime(2026, 5, 1, 0, 0))
    await storage.save_draft("new", "w", "r", datetime.datetime(2026, 5, 3, 0, 0))
    await storage.save_draft("mid", "w", "r", datetime.datetime(2026, 5, 2, 0, 0))
    uc = ListDraftsUseCase(storage=storage)
    drafts = await uc.execute()
    assert [d.slug for d in drafts] == ["new", "mid", "old"]


async def test_list_drafts_since_filter_excludes_older() -> None:
    storage = InMemoryDraftStorage()
    await storage.save_draft("old", "w", "r", datetime.datetime(2026, 5, 1, 0, 0))
    await storage.save_draft("new", "w", "r", datetime.datetime(2026, 5, 3, 0, 0))
    uc = ListDraftsUseCase(storage=storage)
    cutoff = datetime.datetime(2026, 5, 2, 0, 0)
    drafts = await uc.execute(since=cutoff)
    assert [d.slug for d in drafts] == ["new"]


async def test_list_drafts_returns_draft_metadata_instances() -> None:
    storage = InMemoryDraftStorage()
    await storage.save_draft("puey", "w", "r", datetime.datetime(2026, 5, 3, 12, 0, 0))
    uc = ListDraftsUseCase(storage=storage)
    drafts = await uc.execute()
    assert all(isinstance(d, DraftMetadata) for d in drafts)
    assert drafts[0].when == datetime.date(2026, 5, 3)
