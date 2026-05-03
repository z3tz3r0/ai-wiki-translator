"""Tests for `TranslateArticleUseCase` · the Phase 3 orchestrator."""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest

from app.application.dto import Draft, TranslateArticleCommand
from app.application.services.quality_gate import QualityGate
from app.application.use_cases.translate_article import TranslateArticleUseCase
from app.domain.entities import Article
from app.domain.values import ArticleTitle
from tests.fakes.repos import FakeGlossaryRepo, FakePromptRepo
from tests.fakes.storage import InMemoryDraftStorage
from tests.fakes.translators import FakeLLMTranslator, FakeMachineTranslator
from tests.fakes.wikidata import FakeWikidataReader
from tests.fakes.wikipedia import FakeWikipediaReader

FROZEN_NOW = datetime.datetime(2026, 5, 3, 12, 0, 0)
TH_TITLE = "ความหลงตนเอง"
EN_TITLE = "Narcissism"
JA_TITLE = "ナルシシズム"


# --- spies ------------------------------------------------------------------


class CountingMachine(FakeMachineTranslator):
    def __init__(self) -> None:
        self.translate_calls: list[tuple[str, str, str]] = []
        self.batch_calls: list[tuple[tuple[str, ...], str, str]] = []

    async def translate(self, text: str, src: str, tgt: str) -> str:
        self.translate_calls.append((text, src, tgt))
        return await super().translate(text, src, tgt)

    async def translate_batch(self, texts: list[str], src: str, tgt: str) -> list[str]:
        self.batch_calls.append((tuple(texts), src, tgt))
        return await super().translate_batch(texts, src, tgt)


class CountingLLM(FakeLLMTranslator):
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def translate_section(self, content: str, system_instruction: str) -> str:
        self.calls.append((content, system_instruction))
        return await super().translate_section(content, system_instruction)


# --- article builders -------------------------------------------------------


_BIG_FILLER = " ".join([f"word{i}" for i in range(700)])


def _good_source_article(title: str = EN_TITLE) -> Article:
    """≥ 500 words and ≥ 3 refs · passes the default QualityGate."""
    wikitext = (
        "== Introduction ==\n\n"
        f"{_BIG_FILLER} <ref>r1</ref><ref>r2</ref><ref>r3</ref>\n\n"
        "This paragraph mentions [[Ego]] and [[Self]].\n\n"
        "[[File:photo.jpg|thumb|A description]]\n\n"
        "{{blockquote|A quoted passage}}\n\n"
        "* A bullet item\n\n"
        "[[Category:Psychology]]\n"
    )
    wikitext_no_ref = wikitext.replace("<ref>r1</ref><ref>r2</ref><ref>r3</ref>", "[1][2][3]")
    ref_map = {
        "[1]": "<ref>r1</ref>",
        "[2]": "<ref>r2</ref>",
        "[3]": "<ref>r3</ref>",
    }
    return Article(
        title=ArticleTitle(title),
        wikitext=wikitext,
        wikitext_no_ref=wikitext_no_ref,
        ref_map=ref_map,
        wikilinks=["Ego", "Self"],
        dictionary={"Ego": "อีโก้", "Self": "ตัวตน"},
    )


def _short_source_article(title: str = EN_TITLE) -> Article:
    """A few words · fails the default QualityGate."""
    return Article(
        title=ArticleTitle(title),
        wikitext="too short",
        wikitext_no_ref="too short",
        ref_map={},
        wikilinks=[],
        dictionary={},
    )


# --- shared use-case factory ------------------------------------------------


def _make_use_case(
    *,
    wikipedia: FakeWikipediaReader,
    wikidata: FakeWikidataReader | None = None,
    machine: CountingMachine | None = None,
    llm: CountingLLM | None = None,
    prompt_repo: FakePromptRepo | None = None,
    glossary_repo: FakeGlossaryRepo | None = None,
    storage: InMemoryDraftStorage | None = None,
    locale_to_lang: dict[str, str] | None = None,
    quality_gate: QualityGate | None = None,
) -> TranslateArticleUseCase:
    return TranslateArticleUseCase(
        wikipedia=wikipedia,
        wikidata=wikidata or FakeWikidataReader(),
        machine=machine or CountingMachine(),
        llm=llm or CountingLLM(),
        prompt_repo=prompt_repo or FakePromptRepo({"system_instruction_th": "sys"}),
        glossary_repo=glossary_repo or FakeGlossaryRepo(),
        storage=storage or InMemoryDraftStorage(),
        locale_to_lang=locale_to_lang if locale_to_lang is not None else {},
        quality_gate=quality_gate or QualityGate(),
        clock=lambda: FROZEN_NOW,
    )


# --- happy path -------------------------------------------------------------


async def test_happy_path_returns_draft_with_wikitext_and_review() -> None:
    src = _good_source_article()
    th_article = Article(
        title=ArticleTitle(TH_TITLE),
        wikitext="เนื้อหาเดิมในวิกิไทย",
        wikitext_no_ref="เนื้อหาเดิมในวิกิไทย",
        ref_map={},
        wikilinks=[],
        dictionary={},
    )
    storage = InMemoryDraftStorage()
    uc = _make_use_case(
        wikipedia=FakeWikipediaReader(
            articles={
                (TH_TITLE, "th"): th_article,
                (EN_TITLE, "en"): src,
            },
            langlinks={(TH_TITLE, "th"): {"en": EN_TITLE}},
        ),
        storage=storage,
    )
    draft = await uc.execute(TranslateArticleCommand(title=TH_TITLE))

    assert isinstance(draft, Draft)
    assert draft.source_lang == "en"
    assert draft.validation.passed is True
    assert draft.wikitext  # non-empty proposed wikitext
    assert "## Source" in draft.review_md  # review markdown
    drafts = await storage.list_drafts()
    assert len(drafts) == 1
    assert drafts[0].slug == draft.slug


async def test_happy_path_score_carries_real_word_and_ref_counts() -> None:
    src = _good_source_article()
    uc = _make_use_case(
        wikipedia=FakeWikipediaReader(
            articles={(EN_TITLE, "en"): src},
            langlinks={(TH_TITLE, "th"): {"en": EN_TITLE}},
        ),
    )
    draft = await uc.execute(TranslateArticleCommand(title=TH_TITLE))
    assert draft.source_score.word_count > 500
    assert draft.source_score.ref_count == 3


# --- source-picker integration ---------------------------------------------


async def test_source_picker_locale_wins_when_claim_matches() -> None:
    src_ja = _good_source_article(JA_TITLE)
    uc = _make_use_case(
        wikipedia=FakeWikipediaReader(
            articles={(JA_TITLE, "ja"): src_ja},
            langlinks={(TH_TITLE, "th"): {"en": EN_TITLE, "ja": JA_TITLE}},
        ),
        wikidata=FakeWikidataReader(
            qids={(TH_TITLE, "th"): "Q42"},
            claims={"Q42": {"P17": ["Japan"]}},
        ),
        locale_to_lang={"Japan": "ja"},
    )
    draft = await uc.execute(TranslateArticleCommand(title=TH_TITLE))
    assert draft.source_lang == "ja"
    assert draft.source_score.winning_signal == "locale"


async def test_source_picker_falls_back_to_en_when_no_claim_hits() -> None:
    src = _good_source_article()
    uc = _make_use_case(
        wikipedia=FakeWikipediaReader(
            articles={(EN_TITLE, "en"): src},
            langlinks={(TH_TITLE, "th"): {"en": EN_TITLE, "ja": JA_TITLE}},
        ),
        wikidata=FakeWikidataReader(
            qids={(TH_TITLE, "th"): "Q42"},
            claims={"Q42": {"P17": ["United States"]}},
        ),
        locale_to_lang={"Japan": "ja"},
    )
    draft = await uc.execute(TranslateArticleCommand(title=TH_TITLE))
    assert draft.source_lang == "en"
    assert draft.source_score.winning_signal == "fallback_en"


async def test_source_picker_override_uses_user_specified_lang() -> None:
    src_ja = _good_source_article(JA_TITLE)
    uc = _make_use_case(
        wikipedia=FakeWikipediaReader(
            articles={(JA_TITLE, "ja"): src_ja},
            langlinks={(TH_TITLE, "th"): {"en": EN_TITLE, "ja": JA_TITLE}},
        ),
    )
    draft = await uc.execute(
        TranslateArticleCommand(title=TH_TITLE, source_lang_override="ja"),
    )
    assert draft.source_lang == "ja"
    assert draft.source_score.winning_signal == "override"


async def test_override_not_in_langlinks_rejects() -> None:
    uc = _make_use_case(
        wikipedia=FakeWikipediaReader(
            langlinks={(TH_TITLE, "th"): {"en": EN_TITLE}},  # no "ja"
        ),
    )
    draft = await uc.execute(
        TranslateArticleCommand(title=TH_TITLE, source_lang_override="ja"),
    )
    assert draft.validation.passed is False
    assert any("ja" in r for r in draft.validation.reasons)
    assert draft.wikitext == ""


async def test_no_langlinks_rejects() -> None:
    uc = _make_use_case(wikipedia=FakeWikipediaReader())
    draft = await uc.execute(TranslateArticleCommand(title=TH_TITLE))
    assert draft.validation.passed is False
    assert any("langlink" in r.lower() for r in draft.validation.reasons)


# --- translation paths ------------------------------------------------------


async def test_text_blocks_use_llm_path() -> None:
    src = _good_source_article()
    llm = CountingLLM()
    uc = _make_use_case(
        wikipedia=FakeWikipediaReader(
            articles={(EN_TITLE, "en"): src},
            langlinks={(TH_TITLE, "th"): {"en": EN_TITLE}},
        ),
        llm=llm,
    )
    draft = await uc.execute(TranslateArticleCommand(title=TH_TITLE))
    assert llm.calls, "expected at least one TEXT block routed to LLM"
    assert "[llm:" in draft.wikitext


async def test_image_quote_bullet_blocks_do_not_call_llm() -> None:
    """IMAGE / QUOTE / BULLET blocks bypass the LLM path."""
    image_only_wikitext = "[[File:photo.jpg|thumb|A description]]"
    quote_only_wikitext = "{{blockquote|A quoted passage}}"
    bullet_only_wikitext = "* A bullet item"
    for wikitext in (image_only_wikitext, quote_only_wikitext, bullet_only_wikitext):
        src = Article(
            title=ArticleTitle(EN_TITLE),
            wikitext=wikitext,
            wikitext_no_ref=wikitext,
            ref_map={},
            wikilinks=[],
            dictionary={},
        )
        llm = CountingLLM()
        uc = _make_use_case(
            wikipedia=FakeWikipediaReader(
                articles={(EN_TITLE, "en"): src},
                langlinks={(TH_TITLE, "th"): {"en": EN_TITLE}},
            ),
            llm=llm,
            quality_gate=QualityGate(min_word_count=0, min_ref_count=0),
        )
        await uc.execute(TranslateArticleCommand(title=TH_TITLE))
        assert llm.calls == [], f"unexpected LLM call for {wikitext!r}"


async def test_text_blocks_translated_in_serial_order() -> None:
    """TEXT blocks must be translated FIFO (rate-limit / serial ordering).

    Asserts the LLM saw block content in source order. Distinct content per
    block keeps the assertion meaningful · the prior `indices == sorted` form
    was a no-op.
    """
    wikitext = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph.\n"
    src = Article(
        title=ArticleTitle(EN_TITLE),
        wikitext=wikitext,
        wikitext_no_ref=wikitext,
        ref_map={},
        wikilinks=[],
        dictionary={},
    )
    llm = CountingLLM()
    uc = _make_use_case(
        wikipedia=FakeWikipediaReader(
            articles={(EN_TITLE, "en"): src},
            langlinks={(TH_TITLE, "th"): {"en": EN_TITLE}},
        ),
        llm=llm,
        quality_gate=QualityGate(min_word_count=0, min_ref_count=0),
    )
    await uc.execute(TranslateArticleCommand(title=TH_TITLE))
    contents = [c for c, _ in llm.calls]
    assert contents == [
        "First paragraph.",
        "Second paragraph.",
        "Third paragraph.",
    ]


async def test_dictionary_enrichment_runs_at_most_once() -> None:
    """machine.translate_batch is called at most once per article."""
    src = _good_source_article()
    machine = CountingMachine()
    uc = _make_use_case(
        wikipedia=FakeWikipediaReader(
            articles={(EN_TITLE, "en"): src},
            langlinks={(TH_TITLE, "th"): {"en": EN_TITLE}},
        ),
        machine=machine,
    )
    await uc.execute(TranslateArticleCommand(title=TH_TITLE))
    assert len(machine.batch_calls) <= 1


async def test_dictionary_enrichment_translates_unknown_wikilinks_in_batch() -> None:
    """Wikilinks NOT in the article dictionary are batch-translated once."""
    wikitext = "Body referencing [[Unknown1]] and [[Unknown2]] terms."
    src = Article(
        title=ArticleTitle(EN_TITLE),
        wikitext=wikitext,
        wikitext_no_ref=wikitext,
        ref_map={},
        wikilinks=["Unknown1", "Unknown2"],
        dictionary={},
    )
    machine = CountingMachine()
    uc = _make_use_case(
        wikipedia=FakeWikipediaReader(
            articles={(EN_TITLE, "en"): src},
            langlinks={(TH_TITLE, "th"): {"en": EN_TITLE}},
        ),
        machine=machine,
        quality_gate=QualityGate(min_word_count=0, min_ref_count=0),
    )
    await uc.execute(TranslateArticleCommand(title=TH_TITLE))
    assert len(machine.batch_calls) == 1
    sent_texts, src_lang, tgt_lang = machine.batch_calls[0]
    assert set(sent_texts) == {"Unknown1", "Unknown2"}
    assert src_lang == "en"
    assert tgt_lang == "th"


# --- references / pass-through ---------------------------------------------


async def test_reference_markers_restored_in_output() -> None:
    src = _good_source_article()
    uc = _make_use_case(
        wikipedia=FakeWikipediaReader(
            articles={(EN_TITLE, "en"): src},
            langlinks={(TH_TITLE, "th"): {"en": EN_TITLE}},
        ),
    )
    draft = await uc.execute(TranslateArticleCommand(title=TH_TITLE))
    assert "<ref>r1</ref>" in draft.wikitext
    assert "<ref>r2</ref>" in draft.wikitext
    assert "<ref>r3</ref>" in draft.wikitext


async def test_category_blocks_pass_through_unchanged() -> None:
    wikitext = "[[Category:Psychology]]"
    src = Article(
        title=ArticleTitle(EN_TITLE),
        wikitext=wikitext,
        wikitext_no_ref=wikitext,
        ref_map={},
        wikilinks=[],
        dictionary={},
    )
    uc = _make_use_case(
        wikipedia=FakeWikipediaReader(
            articles={(EN_TITLE, "en"): src},
            langlinks={(TH_TITLE, "th"): {"en": EN_TITLE}},
        ),
        quality_gate=QualityGate(min_word_count=0, min_ref_count=0),
    )
    draft = await uc.execute(TranslateArticleCommand(title=TH_TITLE))
    assert "[[Category:Psychology]]" in draft.wikitext


# --- quality-gate rejection -----------------------------------------------


async def test_quality_gate_failure_returns_rejection_draft() -> None:
    short = _short_source_article()
    storage = InMemoryDraftStorage()
    uc = _make_use_case(
        wikipedia=FakeWikipediaReader(
            articles={(EN_TITLE, "en"): short},
            langlinks={(TH_TITLE, "th"): {"en": EN_TITLE}},
        ),
        storage=storage,
    )
    draft = await uc.execute(TranslateArticleCommand(title=TH_TITLE))
    assert draft.validation.passed is False
    assert draft.validation.reasons
    assert draft.wikitext == ""
    assert "rejected" in draft.review_md.lower() or "fail" in draft.review_md.lower()
    assert (await storage.list_drafts())[0].slug == draft.slug


# --- source-not-found rejection -------------------------------------------


async def test_missing_source_article_rejects() -> None:
    """Picker chose a lang but its article isn't fetchable."""
    uc = _make_use_case(
        wikipedia=FakeWikipediaReader(
            langlinks={(TH_TITLE, "th"): {"en": EN_TITLE}},
        ),
    )
    draft = await uc.execute(TranslateArticleCommand(title=TH_TITLE))
    assert draft.validation.passed is False
    assert any("not" in r.lower() and "found" in r.lower() for r in draft.validation.reasons)


# --- new-article path -----------------------------------------------------


async def test_no_th_article_treated_as_new_article_in_review() -> None:
    src = _good_source_article()
    uc = _make_use_case(
        wikipedia=FakeWikipediaReader(
            articles={(EN_TITLE, "en"): src},
            langlinks={(TH_TITLE, "th"): {"en": EN_TITLE}},
        ),
    )
    draft = await uc.execute(TranslateArticleCommand(title=TH_TITLE))
    assert "new article" in draft.review_md.lower()


# --- storage interaction --------------------------------------------------


async def test_use_case_passes_clock_to_storage() -> None:
    """Storage receives the injected clock value · enables deterministic dirs."""
    src = _good_source_article()
    storage = InMemoryDraftStorage()
    uc = _make_use_case(
        wikipedia=FakeWikipediaReader(
            articles={(EN_TITLE, "en"): src},
            langlinks={(TH_TITLE, "th"): {"en": EN_TITLE}},
        ),
        storage=storage,
    )
    await uc.execute(TranslateArticleCommand(title=TH_TITLE))
    drafts = await storage.list_drafts()
    assert drafts[0].when == FROZEN_NOW.date()
    assert drafts[0].dir == Path("/inmemory") / FROZEN_NOW.date().isoformat() / drafts[0].slug


async def test_glossary_path_passed_through_to_repo() -> None:
    """The user's --glossary path reaches the GlossaryRepository."""
    src = _good_source_article()
    seen_paths: list[str | None] = []

    class RecordingGlossaryRepo(FakeGlossaryRepo):
        async def load(self, path: str | None) -> dict[str, str]:
            seen_paths.append(path)
            return await super().load(path)

    uc = _make_use_case(
        wikipedia=FakeWikipediaReader(
            articles={(EN_TITLE, "en"): src},
            langlinks={(TH_TITLE, "th"): {"en": EN_TITLE}},
        ),
        glossary_repo=RecordingGlossaryRepo(),
    )
    await uc.execute(
        TranslateArticleCommand(title=TH_TITLE, glossary_path="glossary.txt"),
    )
    assert seen_paths == ["glossary.txt"]


# --- slug ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "expected_substr"),
    [
        ("Narcissism", "narcissism"),
        ("Some Article With Spaces", "some-article-with-spaces"),
    ],
)
async def test_slug_is_filename_safe(title: str, expected_substr: str) -> None:
    src = _good_source_article()
    uc = _make_use_case(
        wikipedia=FakeWikipediaReader(
            articles={(EN_TITLE, "en"): src},
            langlinks={(title, "th"): {"en": EN_TITLE}},
        ),
    )
    draft = await uc.execute(TranslateArticleCommand(title=title))
    assert expected_substr in draft.slug


async def test_slug_preserves_thai_combining_marks() -> None:
    """Thai vowel signs and tone marks (Unicode Mn) must survive slugify.

    Without this, ``ปรัชญา`` and ``ปรชญา`` collide to the same on-disk
    directory and overwrite each other's draft.
    """
    src = _good_source_article()
    title_with_marks = "ปรัชญา"
    title_without_marks = "ปรชญา"
    uc = _make_use_case(
        wikipedia=FakeWikipediaReader(
            articles={(EN_TITLE, "en"): src},
            langlinks={
                (title_with_marks, "th"): {"en": EN_TITLE},
                (title_without_marks, "th"): {"en": EN_TITLE},
            },
        ),
    )
    draft_a = await uc.execute(TranslateArticleCommand(title=title_with_marks))
    draft_b = await uc.execute(TranslateArticleCommand(title=title_without_marks))
    assert draft_a.slug != draft_b.slug
    assert "ั" in draft_a.slug  # combining vowel sign present


# --- early-rejection persistence (HIGH from python-reviewer) ---------------


async def test_no_langlinks_rejection_persists_to_storage() -> None:
    """Even pre-source rejections write a draft so the reviewer finds it."""
    storage = InMemoryDraftStorage()
    uc = _make_use_case(wikipedia=FakeWikipediaReader(), storage=storage)
    draft = await uc.execute(TranslateArticleCommand(title=TH_TITLE))
    assert draft.validation.passed is False
    saved = await storage.list_drafts()
    assert len(saved) == 1
    assert saved[0].slug == draft.slug


async def test_override_mismatch_rejection_persists_to_storage() -> None:
    storage = InMemoryDraftStorage()
    uc = _make_use_case(
        wikipedia=FakeWikipediaReader(
            langlinks={(TH_TITLE, "th"): {"en": EN_TITLE}},
        ),
        storage=storage,
    )
    draft = await uc.execute(
        TranslateArticleCommand(title=TH_TITLE, source_lang_override="ja"),
    )
    assert draft.validation.passed is False
    saved = await storage.list_drafts()
    assert len(saved) == 1
    assert saved[0].slug == draft.slug


async def test_missing_source_article_rejection_persists_to_storage() -> None:
    storage = InMemoryDraftStorage()
    uc = _make_use_case(
        wikipedia=FakeWikipediaReader(
            langlinks={(TH_TITLE, "th"): {"en": EN_TITLE}},
        ),
        storage=storage,
    )
    draft = await uc.execute(TranslateArticleCommand(title=TH_TITLE))
    assert draft.validation.passed is False
    saved = await storage.list_drafts()
    assert len(saved) == 1
    assert saved[0].slug == draft.slug


async def test_pre_source_rejection_uses_error_winning_signal() -> None:
    """Source picks that fail label the score ``error`` (not a fake fallback)."""
    uc = _make_use_case(wikipedia=FakeWikipediaReader())
    draft = await uc.execute(TranslateArticleCommand(title=TH_TITLE))
    assert draft.source_score.winning_signal == "error"
