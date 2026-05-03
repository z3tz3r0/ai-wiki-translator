"""Tests for `summarize_diff` · the real Phase-3 implementation."""

from __future__ import annotations

import pytest

from app.application.dto import ReviewNotes, SourceScore, ValidationResult
from app.application.services.diff_summary import summarize_diff


def _score(lang: str = "en") -> SourceScore:
    return SourceScore(
        lang=lang,
        word_count=0,
        ref_count=0,
        locale_match=False,
        winning_signal="fallback_en",
    )


def _validation_pass() -> ValidationResult:
    return ValidationResult(passed=True, reasons=())


def test_summarize_diff_returns_review_notes() -> None:
    notes = summarize_diff(
        source_lang="en",
        source_score=_score(),
        validation=_validation_pass(),
        current_th_wikitext="",
        proposed_wikitext="hello",
    )
    assert isinstance(notes, ReviewNotes)
    assert notes.source_lang == "en"
    assert notes.validation.passed is True


def test_summarize_diff_new_article_when_current_blank() -> None:
    notes = summarize_diff(
        source_lang="en",
        source_score=_score(),
        validation=_validation_pass(),
        current_th_wikitext="",
        proposed_wikitext="some new translated wikitext",
    )
    assert "new article" in notes.diff_summary.lower()


def test_summarize_diff_no_changes_when_identical() -> None:
    same = "identical wikitext\nline two"
    notes = summarize_diff(
        source_lang="en",
        source_score=_score(),
        validation=_validation_pass(),
        current_th_wikitext=same,
        proposed_wikitext=same,
    )
    assert "no changes" in notes.diff_summary.lower()


def test_summarize_diff_unified_diff_includes_add_remove_markers() -> None:
    notes = summarize_diff(
        source_lang="en",
        source_score=_score(),
        validation=_validation_pass(),
        current_th_wikitext="line one\nline two\nline three\n",
        proposed_wikitext="line one\nLINE TWO\nline three\n",
    )
    assert "-line two" in notes.diff_summary
    assert "+LINE TWO" in notes.diff_summary


def test_summarize_diff_wraps_diff_in_fenced_block() -> None:
    notes = summarize_diff(
        source_lang="en",
        source_score=_score(),
        validation=_validation_pass(),
        current_th_wikitext="alpha\n",
        proposed_wikitext="beta\n",
    )
    assert notes.diff_summary.startswith("```diff")
    assert notes.diff_summary.rstrip().endswith("```")


def test_summarize_diff_propagates_failed_validation_into_notes() -> None:
    failure = ValidationResult(passed=False, reasons=("too short",))
    notes = summarize_diff(
        source_lang="ja",
        source_score=_score("ja"),
        validation=failure,
        current_th_wikitext="",
        proposed_wikitext="",
    )
    assert notes.validation is failure
    assert notes.source_lang == "ja"


@pytest.mark.parametrize("blank", ["", "   ", "\n\n"])
def test_summarize_diff_treats_whitespace_only_current_as_new(blank: str) -> None:
    notes = summarize_diff(
        source_lang="en",
        source_score=_score(),
        validation=_validation_pass(),
        current_th_wikitext=blank,
        proposed_wikitext="anything",
    )
    assert "new article" in notes.diff_summary.lower()
