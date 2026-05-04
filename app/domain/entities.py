"""Domain entities: Article, Section."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

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
    """Source-language Wikipedia article ready for translation.

    Field semantics (load-bearing for callers, do not mix up):

    * ``wikitext`` · raw MediaWiki source verbatim · contains ``<ref>`` tags
      and HTML comments. Use this only for diff'ing against the live wiki.
    * ``wikitext_no_ref`` · refs replaced with ``[1]``, ``[2]``, ... and
      comments stripped. This is the text fed to the translation pipeline.
    * ``ref_map`` · inverse of the above; pass to ``restore_references`` at
      the end of translation to put the original ``<ref>`` tags back.
    * ``wikilinks`` · de-duplicated wikilink targets in source order.
    * ``dictionary`` · pre-computed wikilink translations (langlink-derived).
      The use case may enrich this via the machine translator at runtime.
    """

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
