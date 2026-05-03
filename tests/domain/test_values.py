"""Domain value object tests."""

from __future__ import annotations

from app.domain.values import (
    ArticleTitle,
    ExecutionMode,
    SectionType,
)


def test_section_type_image_value() -> None:
    assert SectionType.IMAGE.value == "image"


def test_execution_mode_has_async_and_fifo() -> None:
    assert ExecutionMode.ASYNC.value == "ASYNC"
    assert ExecutionMode.FIFO.value == "FIFO"


def test_article_title_is_str_newtype() -> None:
    title = ArticleTitle("Narcissism")
    assert title == "Narcissism"
