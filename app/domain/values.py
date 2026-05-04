"""Domain value objects: enums and type aliases."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import NewType

ArticleTitle = NewType("ArticleTitle", str)

type Glossary = dict[str, str]
type Dictionary = Mapping[str, str]


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
