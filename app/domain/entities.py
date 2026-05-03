"""Domain entities: Article, Section, TranslationJob, TranslatedArticle."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from app.domain.values import (
    ArticleTitle,
    Dictionary,
    ExecutionMode,
    JobId,
    JobStatus,
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
    ref_map: Mapping[str, str]
    wikilinks: tuple[str, ...]
    dictionary: Dictionary

    def __post_init__(self) -> None:
        if not self.title:
            raise ValueError("title must not be empty")
        object.__setattr__(self, "ref_map", MappingProxyType(dict(self.ref_map)))
        object.__setattr__(self, "wikilinks", tuple(self.wikilinks))
        object.__setattr__(self, "dictionary", MappingProxyType(dict(self.dictionary)))


@dataclass
class TranslationJob:
    job_id: JobId
    title: ArticleTitle
    status: JobStatus = JobStatus.PENDING
    result: str | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        if not self.title:
            raise ValueError("title must not be empty")
        if self.status is JobStatus.DONE and not self.result:
            raise ValueError("done jobs must have a result")
        if self.status is JobStatus.FAILED and not self.error:
            raise ValueError("failed jobs must have an error")
        if self.status is not JobStatus.DONE and self.result is not None:
            raise ValueError("only done jobs can have a result")
        if self.status is not JobStatus.FAILED and self.error is not None:
            raise ValueError("only failed jobs can have an error")

    def mark_running(self) -> None:
        if self.status is not JobStatus.PENDING:
            raise ValueError(f"cannot start a job in status {self.status.value}")
        self.status = JobStatus.RUNNING

    def mark_done(self, result: str) -> None:
        if self.status is not JobStatus.RUNNING:
            raise ValueError(f"cannot complete a job in status {self.status.value}")
        if not result:
            raise ValueError("result must not be empty")
        self.status = JobStatus.DONE
        self.result = result

    def mark_failed(self, error: str) -> None:
        if self.status not in (JobStatus.PENDING, JobStatus.RUNNING):
            raise ValueError(f"cannot fail a job in status {self.status.value}")
        if not error:
            raise ValueError("error must not be empty")
        self.status = JobStatus.FAILED
        self.error = error

    def mark_cancelled(self) -> None:
        if self.status not in (JobStatus.PENDING, JobStatus.RUNNING):
            raise ValueError(f"cannot cancel a job in status {self.status.value}")
        self.status = JobStatus.CANCELLED


@dataclass(frozen=True)
class TranslatedArticle:
    job_id: JobId
    title: ArticleTitle
    wikitext: str
