"""Pure-function quality gate · is the candidate source good enough to translate?"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.application.dto import ValidationResult
from app.domain.entities import Article


@dataclass(frozen=True)
class QualityGate:
    """Configurable thresholds for `is_acceptable_source`."""

    min_word_count: int = 500
    min_ref_count: int = 3
    required_sections: frozenset[str] = field(default_factory=frozenset)


def is_acceptable_source(article: Article, gate: QualityGate) -> ValidationResult:
    """Return a `ValidationResult` listing all reasons the article fails the gate.

    Pure function · no I/O. Multiple violations accumulate into `reasons`.
    """
    reasons: list[str] = []

    # NOTE: whitespace split undercounts CJK/Thai text (no word boundaries).
    # The gate is intentionally run on the chosen source article (typically a
    # Latin-script wiki). Phase 3 should not invoke this on Thai wikitext.
    word_count = len(article.wikitext_no_ref.split())
    if word_count < gate.min_word_count:
        reasons.append(f"word count {word_count} below threshold {gate.min_word_count}")

    ref_count = len(article.ref_map)
    if ref_count < gate.min_ref_count:
        reasons.append(f"ref count {ref_count} below threshold {gate.min_ref_count}")

    for header in gate.required_sections:
        if header not in article.wikitext:
            reasons.append(f"required section missing: {header}")

    return ValidationResult(passed=not reasons, reasons=tuple(reasons))
