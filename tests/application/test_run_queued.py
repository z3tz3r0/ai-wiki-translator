"""Tests for `RunQueuedTranslationsUseCase` and `parse_queue_toml`."""

from __future__ import annotations

import datetime

import pytest

from app.application.dto import Draft, TranslateArticleCommand
from app.application.services.quality_gate import QualityGate
from app.application.use_cases.run_queued import (
    RunQueuedTranslationsUseCase,
    parse_queue_toml,
)
from app.application.use_cases.translate_article import TranslateArticleUseCase
from app.domain.entities import Article
from app.domain.values import ArticleTitle
from tests.fakes.repos import FakeGlossaryRepo, FakePromptRepo
from tests.fakes.storage import InMemoryDraftStorage
from tests.fakes.translators import FakeLLMTranslator, FakeMachineTranslator
from tests.fakes.wikidata import FakeWikidataReader
from tests.fakes.wikipedia import FakeWikipediaReader

FROZEN_NOW = datetime.datetime(2026, 5, 3, 12, 0, 0)


# --- TOML parsing -----------------------------------------------------------


def test_parse_queue_toml_empty_body_returns_empty_list() -> None:
    assert parse_queue_toml("") == []


def test_parse_queue_toml_single_entry() -> None:
    cmds = parse_queue_toml(
        """
        [[entry]]
        title = "Narcissism"
        """
    )
    assert cmds == [TranslateArticleCommand(title="Narcissism")]


def test_parse_queue_toml_multiple_entries_preserve_order() -> None:
    cmds = parse_queue_toml(
        """
        [[entry]]
        title = "First"

        [[entry]]
        title = "Second"

        [[entry]]
        title = "Third"
        """
    )
    assert [c.title for c in cmds] == ["First", "Second", "Third"]


def test_parse_queue_toml_carries_optional_fields() -> None:
    cmds = parse_queue_toml(
        """
        [[entry]]
        title = "ความหลงตนเอง"
        source_lang = "ja"
        glossary = "glossary.txt"
        """
    )
    assert cmds == [
        TranslateArticleCommand(
            title="ความหลงตนเอง",
            source_lang_override="ja",
            glossary_path="glossary.txt",
        )
    ]


def test_parse_queue_toml_missing_title_raises() -> None:
    with pytest.raises(KeyError, match="title"):
        parse_queue_toml(
            """
            [[entry]]
            source_lang = "en"
            """
        )


def test_parse_queue_toml_malformed_raises_value_error() -> None:
    with pytest.raises(ValueError, match="invalid TOML"):
        parse_queue_toml('[[entry]]\ntitle = "unterminated')


def test_parse_queue_toml_non_string_title_raises_type_error() -> None:
    with pytest.raises(TypeError, match="title"):
        parse_queue_toml(
            """
            [[entry]]
            title = 42
            """
        )


def test_parse_queue_toml_non_string_source_lang_raises_type_error() -> None:
    with pytest.raises(TypeError, match="source_lang"):
        parse_queue_toml(
            """
            [[entry]]
            title = "ok"
            source_lang = 1.5
            """
        )


# --- use case ---------------------------------------------------------------


def _good_article(title: str) -> Article:
    """Long-enough article to pass default QualityGate."""
    body = " ".join(f"word{i}" for i in range(700))
    wikitext = f"== Body ==\n\n{body} <ref>r1</ref><ref>r2</ref><ref>r3</ref>\n\nParagraph one.\n"
    wikitext_no_ref = wikitext.replace("<ref>r1</ref><ref>r2</ref><ref>r3</ref>", "[1][2][3]")
    return Article(
        title=ArticleTitle(title),
        wikitext=wikitext,
        wikitext_no_ref=wikitext_no_ref,
        ref_map={
            "[1]": "<ref>r1</ref>",
            "[2]": "<ref>r2</ref>",
            "[3]": "<ref>r3</ref>",
        },
        wikilinks=(),
        dictionary={},
    )


def _make_translate_use_case(
    *,
    articles: dict[tuple[str, str], Article],
    langlinks: dict[tuple[str, str], dict[str, str]],
    storage: InMemoryDraftStorage,
) -> TranslateArticleUseCase:
    return TranslateArticleUseCase(
        wikipedia=FakeWikipediaReader(articles=articles, langlinks=langlinks),
        wikidata=FakeWikidataReader(),
        machine=FakeMachineTranslator(),
        llm=FakeLLMTranslator(),
        prompt_repo=FakePromptRepo({"system_instruction_th": "sys"}),
        glossary_repo=FakeGlossaryRepo(),
        storage=storage,
        quality_gate=QualityGate(),
        clock=lambda: FROZEN_NOW,
    )


async def test_run_queued_empty_returns_empty() -> None:
    storage = InMemoryDraftStorage()
    inner = _make_translate_use_case(articles={}, langlinks={}, storage=storage)
    uc = RunQueuedTranslationsUseCase(translate=inner)
    assert await uc.execute([]) == []


async def test_run_queued_runs_each_command_in_order() -> None:
    src_a = _good_article("Article A")
    src_b = _good_article("Article B")
    storage = InMemoryDraftStorage()
    inner = _make_translate_use_case(
        articles={
            ("Article A", "en"): src_a,
            ("Article B", "en"): src_b,
        },
        langlinks={
            ("Title-A", "th"): {"en": "Article A"},
            ("Title-B", "th"): {"en": "Article B"},
        },
        storage=storage,
    )
    uc = RunQueuedTranslationsUseCase(translate=inner)
    drafts = await uc.execute(
        [
            TranslateArticleCommand(title="Title-A"),
            TranslateArticleCommand(title="Title-B"),
        ]
    )
    assert len(drafts) == 2
    assert drafts[0].slug == "title-a"
    assert drafts[1].slug == "title-b"
    assert all(isinstance(d, Draft) for d in drafts)


async def test_run_queued_failure_does_not_abort_subsequent_entries() -> None:
    """When one entry rejects, the queue keeps going."""
    src_b = _good_article("Article B")
    storage = InMemoryDraftStorage()
    inner = _make_translate_use_case(
        articles={("Article B", "en"): src_b},
        langlinks={
            ("Title-A", "th"): {},
            ("Title-B", "th"): {"en": "Article B"},
        },
        storage=storage,
    )
    uc = RunQueuedTranslationsUseCase(translate=inner)
    drafts = await uc.execute(
        [
            TranslateArticleCommand(title="Title-A"),
            TranslateArticleCommand(title="Title-B"),
        ]
    )
    assert len(drafts) == 2
    assert drafts[0].validation.passed is False
    assert drafts[1].validation.passed is True
