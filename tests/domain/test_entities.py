"""Domain entity tests."""

from __future__ import annotations

import dataclasses
import uuid

import pytest

from app.domain.entities import Article, Section, TranslationJob
from app.domain.values import (
    ArticleTitle,
    ExecutionMode,
    JobId,
    JobStatus,
    SectionType,
)


def _make_job() -> TranslationJob:
    return TranslationJob(
        job_id=JobId(uuid.uuid4()),
        title=ArticleTitle("Narcissism"),
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


def test_job_starts_in_pending() -> None:
    job = _make_job()
    assert job.status is JobStatus.PENDING


def test_job_mark_running_transitions_to_running() -> None:
    job = _make_job()
    job.mark_running()
    assert job.status is JobStatus.RUNNING


def test_job_lifecycle_pending_to_done() -> None:
    job = _make_job()
    job.mark_running()
    job.mark_done("output wikitext")
    assert job.status is JobStatus.DONE
    assert job.result == "output wikitext"


def test_job_cannot_start_twice() -> None:
    job = _make_job()
    job.mark_running()
    with pytest.raises(ValueError, match="status"):
        job.mark_running()


def test_job_cancel_from_running() -> None:
    job = _make_job()
    job.mark_running()
    job.mark_cancelled()
    assert job.status == JobStatus.CANCELLED


def test_job_cancel_from_done_raises() -> None:
    job = _make_job()
    job.mark_running()
    job.mark_done("result")
    with pytest.raises(ValueError, match="status"):
        job.mark_cancelled()


def test_translation_job_empty_title_raises() -> None:
    with pytest.raises(ValueError, match="title"):
        TranslationJob(job_id=JobId(uuid.uuid4()), title=ArticleTitle(""))


def test_job_done_from_pending_raises() -> None:
    job = _make_job()
    with pytest.raises(ValueError, match="status"):
        job.mark_done("result")


def test_job_mark_failed_sets_status_and_error() -> None:
    job = _make_job()
    job.mark_running()
    job.mark_failed("boom")
    assert job.status == JobStatus.FAILED
    assert job.error == "boom"


def test_job_mark_failed_from_done_raises() -> None:
    """Regression: mark_failed must not silently overwrite a DONE result."""
    job = _make_job()
    job.mark_running()
    job.mark_done("result")
    with pytest.raises(ValueError, match="status"):
        job.mark_failed("late failure")


def test_job_done_without_result_raises() -> None:
    with pytest.raises(ValueError, match="result"):
        TranslationJob(
            job_id=JobId(uuid.uuid4()),
            title=ArticleTitle("T"),
            status=JobStatus.DONE,
            result=None,
        )


def test_job_failed_without_error_raises() -> None:
    with pytest.raises(ValueError, match="error"):
        TranslationJob(
            job_id=JobId(uuid.uuid4()),
            title=ArticleTitle("T"),
            status=JobStatus.FAILED,
            error=None,
        )


def test_job_pending_with_result_raises() -> None:
    with pytest.raises(ValueError, match="result"):
        TranslationJob(
            job_id=JobId(uuid.uuid4()),
            title=ArticleTitle("T"),
            status=JobStatus.PENDING,
            result="early result",
        )


def test_job_pending_with_error_raises() -> None:
    with pytest.raises(ValueError, match="error"):
        TranslationJob(
            job_id=JobId(uuid.uuid4()),
            title=ArticleTitle("T"),
            status=JobStatus.PENDING,
            error="premature error",
        )


def test_mark_done_with_empty_result_raises() -> None:
    job = _make_job()
    job.mark_running()
    with pytest.raises(ValueError, match="result"):
        job.mark_done("")


def test_mark_failed_with_empty_error_raises() -> None:
    job = _make_job()
    job.mark_running()
    with pytest.raises(ValueError, match="error"):
        job.mark_failed("")
