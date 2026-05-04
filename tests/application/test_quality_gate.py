"""Tests for `is_acceptable_source` quality gate."""

from __future__ import annotations

from app.application.services.quality_gate import QualityGate, is_acceptable_source
from app.domain.entities import Article
from app.domain.values import ArticleTitle


def _article(
    title: str = "Foo",
    *,
    word_count: int = 1000,
    ref_count: int = 5,
    extra_wikitext: str = "",
) -> Article:
    body = " ".join(["word"] * word_count)
    return Article(
        title=ArticleTitle(title),
        wikitext=f"{body}\n{extra_wikitext}",
        wikitext_no_ref=body,
        ref_map={f"[{i}]": f"<ref>{i}</ref>" for i in range(1, ref_count + 1)},
        wikilinks=(),
        dictionary={},
    )


def test_quality_gate_passes_adequate_article() -> None:
    result = is_acceptable_source(_article(), QualityGate())
    assert result.passed
    assert result.reasons == ()


def test_quality_gate_fails_too_few_words() -> None:
    result = is_acceptable_source(_article(word_count=10), QualityGate(min_word_count=500))
    assert not result.passed
    assert any("word count" in r for r in result.reasons)


def test_quality_gate_fails_too_few_refs() -> None:
    result = is_acceptable_source(_article(ref_count=0), QualityGate(min_ref_count=3))
    assert not result.passed
    assert any("ref count" in r for r in result.reasons)


def test_quality_gate_fails_multiple() -> None:
    result = is_acceptable_source(
        _article(word_count=10, ref_count=0),
        QualityGate(min_word_count=500, min_ref_count=3),
    )
    assert not result.passed
    assert len(result.reasons) == 2


def test_quality_gate_required_sections_present() -> None:
    result = is_acceptable_source(
        _article(extra_wikitext="==History=="),
        QualityGate(required_sections=frozenset({"==History=="})),
    )
    assert result.passed


def test_quality_gate_required_section_missing() -> None:
    result = is_acceptable_source(
        _article(),
        QualityGate(required_sections=frozenset({"==Career=="})),
    )
    assert not result.passed
    assert any("==Career==" in r for r in result.reasons)


def test_quality_gate_validation_result_reasons_is_tuple() -> None:
    result = is_acceptable_source(_article(), QualityGate())
    assert isinstance(result.reasons, tuple)
