"""Domain entities: Article, Section."""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.values import (
    ArticleTitle,
    Dictionary,
    ExecutionMode,
    SectionType,
)


@dataclass(frozen=True)
class Section:
    task_id: int
    content: str
    section_type: SectionType
    execution_mode: ExecutionMode

    def __post_init__(self) -> None:
        if self.task_id < 1:
            raise ValueError("task_id must be >= 1")


@dataclass(frozen=True)
class Article:
    title: ArticleTitle
    wikitext: str
    wikitext_no_ref: str
    ref_map: dict[str, str]
    wikilinks: list[str]
    dictionary: Dictionary

    def __post_init__(self) -> None:
        if not self.title:
            raise ValueError("title must not be empty")
