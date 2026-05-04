"""Tests for `transliteration_gate` · detection regex + orchestrator."""

from __future__ import annotations

import datetime
from typing import ClassVar

import pytest

from app.application.dto import (
    LanguageRuleSet,
    RuleEntry,
    TransliterationCandidate,
    TransliterationVerdict,
)
from app.application.services.transliteration_gate import (
    detect_candidates,
    evaluate_transliterations,
)
from tests.fakes.validator import FakeTransliterationValidator


def _ruleset(lang: str = "en") -> LanguageRuleSet:
    return LanguageRuleSet(
        lang=lang,
        title=f"rules-{lang}",
        url=f"https://th.wikipedia.org/wiki/rules-{lang}",
        scraped_at=datetime.datetime(2026, 5, 4, 12, 0, 0),
        entries=(RuleEntry(grapheme="A", thai="เอ"),),
        excerpt="| A | เอ |\n|---|---|",
    )


# --- detect_candidates ------------------------------------------------------


def test_detect_finds_thai_inside_wikilink_pipe() -> None:
    wikitext = "[[Anders Hejlsberg|แอนเดอส์ เฮลส์เบิร์ก]] เป็นนักวิทยาศาสตร์"
    out = detect_candidates(wikitext)
    assert len(out) == 1
    assert out[0].thai == "แอนเดอส์ เฮลส์เบิร์ก"
    assert out[0].latin_hint == "Anders Hejlsberg"


def test_detect_finds_thai_followed_by_latin_paren() -> None:
    wikitext = "ภาษาซีชาร์ป (C Sharp) ถูกออกแบบโดย แอนเดอส์ เฮลส์เบิร์ก (Anders Hejlsberg)"
    out = detect_candidates(wikitext)
    thais = [c.thai for c in out]
    assert "แอนเดอส์ เฮลส์เบิร์ก" in thais
    hint = next(c.latin_hint for c in out if c.thai == "แอนเดอส์ เฮลส์เบิร์ก")
    assert hint == "Anders Hejlsberg"


def test_detect_clips_3plus_word_thai_paren_known_limitation() -> None:
    """Pin the last-2-words clip behavior on a real 3-word transliteration.

    The greedy paren regex absorbs the surrounding native-Thai prefix, so
    the detector trims to the last two words. For genuine 3-word names
    like "มาร์ติน ลูเธอร์ คิง" (Martin Luther King) this clips the first
    word. Tracking this as a known v1 limitation · revisit with Phase 4
    eval metrics. If those metrics show the clip hurts FP/recall more
    than it helps, replace this test with one asserting the full 3-word
    emission.
    """
    wikitext = "ผู้ที่ได้รับ มาร์ติน ลูเธอร์ คิง (Martin Luther King) ในปี ..."
    out = detect_candidates(wikitext)
    thais = [c.thai for c in out]
    assert "ลูเธอร์ คิง" in thais
    assert "มาร์ติน ลูเธอร์ คิง" not in thais


def test_detect_skips_single_word_thai() -> None:
    wikitext = "บทความนี้เกี่ยวกับ ภาษา ทั่วไป"
    out = detect_candidates(wikitext)
    assert out == ()


def test_detect_deduplicates_repeated_candidates() -> None:
    wikitext = (
        "[[Anders Hejlsberg|แอนเดอส์ เฮลส์เบิร์ก]] ทำงาน ... "
        "ต่อมา แอนเดอส์ เฮลส์เบิร์ก (Anders Hejlsberg) ก็ ..."
    )
    out = detect_candidates(wikitext)
    thais = [c.thai for c in out]
    assert thais.count("แอนเดอส์ เฮลส์เบิร์ก") == 1


def test_detect_skips_ref_markers() -> None:
    wikitext = "[[REF_1]][[REF_2]] [[Anders Hejlsberg|แอนเดอส์ เฮลส์เบิร์ก]]"
    out = detect_candidates(wikitext)
    assert len(out) == 1
    assert out[0].thai == "แอนเดอส์ เฮลส์เบิร์ก"


def test_detect_returns_tuple() -> None:
    out = detect_candidates("plain text only")
    assert isinstance(out, tuple)
    assert out == ()


def test_detect_context_window_bounds() -> None:
    wikitext = "x" * 50 + "[[T|แอนเดอส์ เฮลส์เบิร์ก]]" + "y" * 200
    out = detect_candidates(wikitext)
    assert len(out) == 1
    # Context radius is 80 chars · should be much smaller than full wikitext.
    assert len(out[0].context) <= len("[[T|แอนเดอส์ เฮลส์เบิร์ก]]") + 160 + 5


# --- evaluate_transliterations · happy path ---------------------------------


async def test_evaluate_returns_skipped_when_rules_none() -> None:
    validator = FakeTransliterationValidator()
    report = await evaluate_transliterations(
        source_lang="en",
        proposed_wikitext="[[X|แอนเดอส์ เฮลส์เบิร์ก]]",
        rules=None,
        validator=validator,
    )
    assert report.status == "skipped"
    assert "wiki-refresh-rules" in report.skipped_reason
    assert report.candidates_found == 0
    assert report.verdicts == ()
    # Validator must not be called when skipped.
    assert validator.calls == []


async def test_evaluate_returns_ok_zero_when_no_candidates() -> None:
    validator = FakeTransliterationValidator()
    report = await evaluate_transliterations(
        source_lang="en",
        proposed_wikitext="ข้อความไทยล้วน ไม่มีทับศัพท์",
        rules=_ruleset(),
        validator=validator,
    )
    assert report.status == "ok"
    assert report.candidates_found == 0
    assert report.verdicts == ()
    assert validator.calls == []


async def test_evaluate_calls_validator_once_with_all_candidates() -> None:
    validator = FakeTransliterationValidator()
    wikitext = "[[A|แอนเดอส์ เฮลส์เบิร์ก]] กับ [[B|มาร์ก ซักเคอร์เบิร์ก]] เป็น ..."
    report = await evaluate_transliterations(
        source_lang="en",
        proposed_wikitext=wikitext,
        rules=_ruleset(),
        validator=validator,
    )
    assert report.status == "ok"
    assert report.candidates_found == 2
    assert len(validator.calls) == 1  # batched
    passed_candidates, passed_rules = validator.calls[0]
    assert len(passed_candidates) == 2
    assert passed_rules.lang == "en"


async def test_evaluate_preserves_verdict_order() -> None:
    validator = FakeTransliterationValidator(
        verdicts_by_thai={
            "แอนเดอส์ เฮลส์เบิร์ก": TransliterationVerdict(
                candidate=TransliterationCandidate(thai="แอนเดอส์ เฮลส์เบิร์ก", context=""),
                status="approved",
            ),
            "มาร์ก ซักเคอร์เบิร์ก": TransliterationVerdict(
                candidate=TransliterationCandidate(thai="มาร์ก ซักเคอร์เบิร์ก", context=""),
                status="flagged",
                suggested="มาร์ก ซักเคอร์เบิร์ค",
            ),
        },
    )
    wikitext = "[[A|แอนเดอส์ เฮลส์เบิร์ก]] กับ [[B|มาร์ก ซักเคอร์เบิร์ก]]"
    report = await evaluate_transliterations(
        source_lang="en",
        proposed_wikitext=wikitext,
        rules=_ruleset(),
        validator=validator,
    )
    thais = [v.candidate.thai for v in report.verdicts]
    assert thais == ["แอนเดอส์ เฮลส์เบิร์ก", "มาร์ก ซักเคอร์เบิร์ก"]


async def test_evaluate_pads_short_validator_response_with_uncertain() -> None:
    class ShortValidator:
        calls: ClassVar[list[tuple[tuple[TransliterationCandidate, ...], LanguageRuleSet]]] = []

        async def validate(
            self,
            candidates: tuple[TransliterationCandidate, ...],
            rules: LanguageRuleSet,
        ) -> tuple[TransliterationVerdict, ...]:
            # Return only one verdict for two candidates.
            return (TransliterationVerdict(candidate=candidates[0], status="approved"),)

    validator = ShortValidator()
    wikitext = "[[A|ก ก ก]] กับ [[B|ข ข ข]]"
    # Use a contrived multi-word Thai to exercise the regex; verify padding.
    report = await evaluate_transliterations(
        source_lang="en",
        proposed_wikitext=wikitext,
        rules=_ruleset(),
        validator=validator,
    )
    assert len(report.verdicts) == 2
    assert report.verdicts[0].status == "approved"
    assert report.verdicts[1].status == "uncertain"
    assert "truncated" in report.verdicts[1].reason


async def test_evaluate_propagates_validator_exception() -> None:
    validator = FakeTransliterationValidator(raises=RuntimeError("boom"))
    with pytest.raises(RuntimeError, match="boom"):
        await evaluate_transliterations(
            source_lang="en",
            proposed_wikitext="[[A|แอนเดอส์ เฮลส์เบิร์ก]]",
            rules=_ruleset(),
            validator=validator,
        )
