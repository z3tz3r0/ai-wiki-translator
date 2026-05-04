"""Domain entity tests."""

from __future__ import annotations

import dataclasses

import pytest

from app.domain.entities import Article, Section
from app.domain.values import (
    ArticleTitle,
    ExecutionMode,
    SectionType,
)


def test_section_frozen() -> None:
    section = Section(
        task_id=1,
        content="hello",
        section_type=SectionType.TEXT,
        execution_mode=ExecutionMode.FIFO,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        section.content = "mutated"  # type: ignore[misc]


def test_section_task_id_zero_raises() -> None:
    with pytest.raises(ValueError, match="task_id"):
        Section(
            task_id=0,
            content="x",
            section_type=SectionType.TEXT,
            execution_mode=ExecutionMode.FIFO,
        )


def test_article_empty_title_raises() -> None:
    with pytest.raises(ValueError, match="title"):
        Article(
            title=ArticleTitle(""),
            wikitext="",
            wikitext_no_ref="",
            ref_map={},
            wikilinks=(),
            dictionary={},
        )
