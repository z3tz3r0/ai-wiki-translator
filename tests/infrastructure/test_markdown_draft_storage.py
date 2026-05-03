"""Tests for `MarkdownDraftStorage` · the disk-backed DraftStorage adapter."""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest

from app.application.dto import DraftMetadata
from app.application.ports import DraftStorage
from app.infrastructure.markdown_draft_storage import MarkdownDraftStorage

# --- Protocol satisfaction --------------------------------------------------


def test_satisfies_draft_storage_protocol(tmp_path: Path) -> None:
    storage = MarkdownDraftStorage(base_dir=tmp_path)
    assert isinstance(storage, DraftStorage)


# --- save_draft -------------------------------------------------------------


async def test_save_draft_creates_date_and_slug_directories(tmp_path: Path) -> None:
    storage = MarkdownDraftStorage(base_dir=tmp_path)
    when = datetime.datetime(2026, 5, 3, 12, 0, 0)
    out_dir = await storage.save_draft("puey", "wikitext body", "review body", when)
    assert out_dir == tmp_path / "2026-05-03" / "puey"
    assert out_dir.is_dir()


async def test_save_draft_writes_wikitext_and_review_files(tmp_path: Path) -> None:
    storage = MarkdownDraftStorage(base_dir=tmp_path)
    when = datetime.datetime(2026, 5, 3, 12, 0, 0)
    out_dir = await storage.save_draft("puey", "wikitext body", "review body", when)
    assert (out_dir / "puey.wikitext").read_text(encoding="utf-8") == "wikitext body"
    assert (out_dir / "puey.review.md").read_text(encoding="utf-8") == "review body"


async def test_save_draft_handles_thai_slug(tmp_path: Path) -> None:
    """Thai-script slug must round-trip through the filesystem cleanly."""
    storage = MarkdownDraftStorage(base_dir=tmp_path)
    when = datetime.datetime(2026, 5, 3, 12, 0, 0)
    out_dir = await storage.save_draft("ความหลงตนเอง", "th wikitext", "th review", when)
    assert out_dir == tmp_path / "2026-05-03" / "ความหลงตนเอง"
    assert (out_dir / "ความหลงตนเอง.wikitext").read_text(encoding="utf-8") == "th wikitext"


async def test_save_draft_idempotent_overwrites_with_bak(tmp_path: Path) -> None:
    """Re-running for the same (date, slug) backs up the prior files as .bak."""
    storage = MarkdownDraftStorage(base_dir=tmp_path)
    when = datetime.datetime(2026, 5, 3, 12, 0, 0)
    await storage.save_draft("puey", "v1 wikitext", "v1 review", when)
    out_dir = await storage.save_draft("puey", "v2 wikitext", "v2 review", when)

    assert (out_dir / "puey.wikitext").read_text(encoding="utf-8") == "v2 wikitext"
    assert (out_dir / "puey.review.md").read_text(encoding="utf-8") == "v2 review"
    assert (out_dir / "puey.wikitext.bak").read_text(encoding="utf-8") == "v1 wikitext"
    assert (out_dir / "puey.review.md.bak").read_text(encoding="utf-8") == "v1 review"


async def test_save_draft_third_run_replaces_existing_bak(tmp_path: Path) -> None:
    """A second overwrite replaces the .bak with the most recent prior content."""
    storage = MarkdownDraftStorage(base_dir=tmp_path)
    when = datetime.datetime(2026, 5, 3, 12, 0, 0)
    await storage.save_draft("puey", "v1", "r1", when)
    await storage.save_draft("puey", "v2", "r2", when)
    out_dir = await storage.save_draft("puey", "v3", "r3", when)

    assert (out_dir / "puey.wikitext").read_text(encoding="utf-8") == "v3"
    assert (out_dir / "puey.wikitext.bak").read_text(encoding="utf-8") == "v2"


async def test_save_draft_returns_path_for_caller(tmp_path: Path) -> None:
    storage = MarkdownDraftStorage(base_dir=tmp_path)
    when = datetime.datetime(2026, 5, 3, 12, 0, 0)
    out_dir = await storage.save_draft("foo", "w", "r", when)
    assert isinstance(out_dir, Path)
    assert out_dir.exists()


# --- path-traversal hardening -----------------------------------------------


@pytest.mark.parametrize(
    "evil",
    [
        "../escape",
        "foo/../../etc",
        "..",
        "/abs/path",
        "",
        "foo\nbar",  # newline · breaks CLI output even though OS allows it
        "foo\tbar",  # tab
        "foo\x00bar",  # null byte
    ],
)
async def test_save_draft_rejects_path_traversal_or_empty_slug(tmp_path: Path, evil: str) -> None:
    storage = MarkdownDraftStorage(base_dir=tmp_path)
    when = datetime.datetime(2026, 5, 3, 12, 0, 0)
    with pytest.raises(ValueError, match="slug"):
        await storage.save_draft(evil, "w", "r", when)


# --- list_drafts ------------------------------------------------------------


async def test_list_drafts_empty_dir_returns_empty(tmp_path: Path) -> None:
    storage = MarkdownDraftStorage(base_dir=tmp_path)
    assert await storage.list_drafts() == []


async def test_list_drafts_returns_descending_order(tmp_path: Path) -> None:
    storage = MarkdownDraftStorage(base_dir=tmp_path)
    await storage.save_draft("old", "w", "r", datetime.datetime(2026, 5, 1))
    await storage.save_draft("mid", "w", "r", datetime.datetime(2026, 5, 2))
    await storage.save_draft("new", "w", "r", datetime.datetime(2026, 5, 3))

    drafts = await storage.list_drafts()
    assert [d.slug for d in drafts] == ["new", "mid", "old"]


async def test_list_drafts_returns_draft_metadata(tmp_path: Path) -> None:
    storage = MarkdownDraftStorage(base_dir=tmp_path)
    when = datetime.datetime(2026, 5, 3, 12, 0, 0)
    await storage.save_draft("puey", "w", "r", when)
    drafts = await storage.list_drafts()
    assert drafts == [
        DraftMetadata(
            slug="puey",
            when=datetime.date(2026, 5, 3),
            dir=tmp_path / "2026-05-03" / "puey",
        )
    ]


async def test_list_drafts_since_filter_excludes_older(tmp_path: Path) -> None:
    storage = MarkdownDraftStorage(base_dir=tmp_path)
    await storage.save_draft("old", "w", "r", datetime.datetime(2026, 5, 1))
    await storage.save_draft("new", "w", "r", datetime.datetime(2026, 5, 3))
    cutoff = datetime.datetime(2026, 5, 2)
    drafts = await storage.list_drafts(since=cutoff)
    assert [d.slug for d in drafts] == ["new"]


async def test_list_drafts_ignores_non_date_dirs(tmp_path: Path) -> None:
    """Stray directories that aren't YYYY-MM-DD are silently skipped."""
    storage = MarkdownDraftStorage(base_dir=tmp_path)
    (tmp_path / "not-a-date").mkdir()
    (tmp_path / "not-a-date" / "junk").mkdir()
    await storage.save_draft("real", "w", "r", datetime.datetime(2026, 5, 3))
    drafts = await storage.list_drafts()
    assert [d.slug for d in drafts] == ["real"]


async def test_list_drafts_skips_loose_files_at_date_root(tmp_path: Path) -> None:
    """Files (not dirs) under a date prefix are ignored."""
    storage = MarkdownDraftStorage(base_dir=tmp_path)
    when = datetime.datetime(2026, 5, 3)
    await storage.save_draft("real", "w", "r", when)
    (tmp_path / "2026-05-03" / "stray.txt").write_text("not a draft", encoding="utf-8")
    drafts = await storage.list_drafts()
    assert [d.slug for d in drafts] == ["real"]


async def test_list_drafts_creates_base_dir_lazily(tmp_path: Path) -> None:
    """list_drafts on a base_dir that doesn't exist yet returns empty without error."""
    nonexistent = tmp_path / "never-created"
    storage = MarkdownDraftStorage(base_dir=nonexistent)
    assert await storage.list_drafts() == []


# --- default user dir construction (no I/O) --------------------------------


def test_default_user_dir_under_documents() -> None:
    """`MarkdownDraftStorage.default_user_dir()` points at ~/Documents/wiki-translations."""
    target = MarkdownDraftStorage.default_user_dir()
    assert target.name == "wiki-translations"
    assert target.parent.name == "Documents"
