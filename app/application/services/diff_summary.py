"""Stub for `summarize_diff` · Phase 3 will replace the body with a real diff."""

from __future__ import annotations

from app.application.dto import ReviewNotes, SourceScore, ValidationResult


def summarize_diff(
    source_lang: str,
    source_score: SourceScore,
    validation: ValidationResult,
    current_th_wikitext: str,
    proposed_wikitext: str,
) -> ReviewNotes:
    """Wrap metadata in a `ReviewNotes` dataclass.

    Phase 2 stub · returns the source/validation metadata with an empty
    `diff_summary`. Phase 3 will replace the body with a section-aware
    diff between `current_th_wikitext` and `proposed_wikitext` so the
    reviewer can spot Thai-only context worth preserving.
    """
    # Parameters are intentionally accepted now to lock in the signature;
    # Phase 3 implementation will consume them.
    _ = (current_th_wikitext, proposed_wikitext)
    return ReviewNotes(
        source_lang=source_lang,
        source_score=source_score,
        validation=validation,
        diff_summary="",
    )
