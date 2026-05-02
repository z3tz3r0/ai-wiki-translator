"""Domain value object tests."""

from __future__ import annotations

import uuid

from app.domain.values import (
    ArticleTitle,
    ExecutionMode,
    JobId,
    JobStatus,
    SectionType,
)


def test_section_type_image_value() -> None:
    assert SectionType.IMAGE.value == "image"


def test_execution_mode_has_async_and_fifo() -> None:
    assert ExecutionMode.ASYNC.value == "ASYNC"
    assert ExecutionMode.FIFO.value == "FIFO"


def test_job_id_is_uuid_newtype() -> None:
    raw = uuid.uuid4()
    job_id = JobId(raw)
    assert job_id == raw


def test_article_title_is_str_newtype() -> None:
    title = ArticleTitle("Narcissism")
    assert title == "Narcissism"


def test_job_status_done_value() -> None:
    assert JobStatus.DONE.value == "done"
