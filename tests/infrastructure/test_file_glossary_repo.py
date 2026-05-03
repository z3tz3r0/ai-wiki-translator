"""Tests for `FileGlossaryRepository`."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.application.ports import GlossaryRepository
from app.infrastructure.file_glossary_repo import FileGlossaryRepository


def test_satisfies_glossary_repo_protocol() -> None:
    assert isinstance(FileGlossaryRepository(), GlossaryRepository)


async def test_load_none_returns_empty_glossary() -> None:
    repo = FileGlossaryRepository()
    assert await repo.load(None) == {}


async def test_load_parses_term_colon_translation_lines(tmp_path: Path) -> None:
    glossary_file = tmp_path / "my_glossary.txt"
    glossary_file.write_text(
        "Foo:ฟู\nBar:บาร์\n# a comment without colon is skipped\n",
        encoding="utf-8",
    )
    repo = FileGlossaryRepository()
    glossary = await repo.load(str(glossary_file))
    assert glossary == {"Foo": "ฟู", "Bar": "บาร์"}


async def test_load_missing_path_raises_file_not_found(tmp_path: Path) -> None:
    repo = FileGlossaryRepository()
    with pytest.raises(FileNotFoundError):
        await repo.load(str(tmp_path / "nope.txt"))


async def test_load_strips_whitespace_around_terms(tmp_path: Path) -> None:
    glossary_file = tmp_path / "g.txt"
    glossary_file.write_text("  Foo  :  ฟู  \n", encoding="utf-8")
    repo = FileGlossaryRepository()
    glossary = await repo.load(str(glossary_file))
    assert glossary == {"Foo": "ฟู"}


async def test_load_empty_file_returns_empty_glossary(tmp_path: Path) -> None:
    glossary_file = tmp_path / "empty.txt"
    glossary_file.write_text("", encoding="utf-8")
    repo = FileGlossaryRepository()
    assert await repo.load(str(glossary_file)) == {}
