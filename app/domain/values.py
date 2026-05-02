"""Domain value objects: enums, NewTypes, and type aliases."""

from __future__ import annotations

import uuid
from enum import StrEnum
from typing import NewType

ArticleTitle = NewType("ArticleTitle", str)
JobId = NewType("JobId", uuid.UUID)

type Glossary = dict[str, str]
type Dictionary = dict[str, str]


class SectionType(StrEnum):
    EMPTY = "empty"
    GLOSSARY = "glossary"
    SECTION_HEADER = "section_header"
    IMAGE = "image"
    QUOTE = "quote"
    BULLET_POINT = "bullet_point"
    CATEGORY = "category"
    TEMPLATE = "template"
    TEXT = "text"


class ExecutionMode(StrEnum):
    ASYNC = "ASYNC"
    FIFO = "FIFO"


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    CANCELLED = "cancelled"
    FAILED = "failed"
