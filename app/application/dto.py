"""Application-layer DTOs and value objects."""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class SourceScore:
    """Result of source-language picking · which lang won and why."""

    lang: str
    word_count: int
    ref_count: int
    locale_match: bool
    winning_signal: Literal["locale", "fallback_en", "first_langlink"]


@dataclass(frozen=True)
class ValidationResult:
    """Quality-gate verdict + reasons (frozen, tuple for immutability)."""

    passed: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ReviewNotes:
    """Body of the `<slug>.review.md` file the user reads before pasting."""

    source_lang: str
    source_score: SourceScore
    validation: ValidationResult
    diff_summary: str  # markdown block; empty until Phase 3 wires summarize_diff


@dataclass(frozen=True)
class DraftMetadata:
    """A draft on disk · slug + the date dir it lives under."""

    slug: str
    when: datetime.date  # date, not datetime, to match the <YYYY-MM-DD>/ dir layout
    dir: Path


@dataclass(frozen=True)
class Draft:
    """The full proposal returned by TranslateArticleUseCase."""

    slug: str
    source_lang: str
    source_score: SourceScore
    validation: ValidationResult
    wikitext: str
    review_md: str


@dataclass(frozen=True)
class TranslateArticleCommand:
    """Input to TranslateArticleUseCase."""

    title: str
    source_lang_override: str | None = None
    glossary_path: str | None = None
    output_dir: Path | None = None
