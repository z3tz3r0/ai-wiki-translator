"""Phase 2 contract tests against the fakes."""

from __future__ import annotations

import dataclasses
import datetime
from pathlib import Path
from typing import Any

import pytest

from app.application.dto import DraftMetadata
from app.application.ports import (
    DraftStorage,
    GlossaryRepository,
    LLMTranslator,
    MachineTranslator,
    PromptTemplateRepository,
    TransliterationValidator,
    WikidataReader,
    WikipediaReader,
)
from app.domain.entities import Article
from app.domain.values import ArticleTitle
from tests.fakes.repos import FakeGlossaryRepo, FakePromptRepo
from tests.fakes.storage import InMemoryDraftStorage
from tests.fakes.translators import FakeLLMTranslator, FakeMachineTranslator
from tests.fakes.validator import FakeTransliterationValidator
from tests.fakes.wikidata import FakeWikidataReader
from tests.fakes.wikipedia import FakeWikipediaReader


def _make_article(title: str = "Foo") -> Article:
    return Article(
        title=ArticleTitle(title),
        wikitext="body",
        wikitext_no_ref="body",
        ref_map={},
        wikilinks=(),
        dictionary={},
    )


# --- FakeWikipediaReader ----------------------------------------------------


async def test_fake_wikipedia_returns_none_for_unknown() -> None:
    reader = FakeWikipediaReader()
    assert await reader.fetch_article("Missing", "en") is None


async def test_fake_wikipedia_returns_article_for_known() -> None:
    article = _make_article("Narcissism")
    reader = FakeWikipediaReader(articles={("Narcissism", "en"): article})
    fetched = await reader.fetch_article("Narcissism", "en")
    assert fetched is article


async def test_fake_wikipedia_fetch_langlinks() -> None:
    reader = FakeWikipediaReader(
        langlinks={("Narcissism", "en"): {"th": "ความหลงตนเอง", "ja": "ナルシシズム"}}
    )
    out = await reader.fetch_langlinks("Narcissism", "en")
    assert out == {"th": "ความหลงตนเอง", "ja": "ナルシシズム"}


# --- FakeWikidataReader -----------------------------------------------------


async def test_fake_wikidata_resolve_qid_found() -> None:
    reader = FakeWikidataReader(qids={("ป๋วย อึ๊งภากรณ์", "th"): "Q713853"})
    assert await reader.resolve_qid("ป๋วย อึ๊งภากรณ์", "th") == "Q713853"


async def test_fake_wikidata_resolve_qid_missing() -> None:
    reader = FakeWikidataReader()
    assert await reader.resolve_qid("Unknown", "en") is None


async def test_fake_wikidata_fetch_claims() -> None:
    reader = FakeWikidataReader(claims={"Q713853": {"P17": ["Thailand"]}})
    out = await reader.fetch_claims("Q713853")
    assert out == {"P17": ["Thailand"]}


# --- FakeMachineTranslator + FakeLLMTranslator ------------------------------


async def test_fake_machine_translate_marks_path() -> None:
    out = await FakeMachineTranslator().translate("hello", "en", "th")
    assert out == "[mt:hello]"


async def test_fake_machine_translate_batch_length() -> None:
    out = await FakeMachineTranslator().translate_batch(["a", "b"], "en", "th")
    assert out == ["[mt:a]", "[mt:b]"]


async def test_fake_llm_translate_marks_path() -> None:
    out = await FakeLLMTranslator().translate_section("paragraph", "system")
    assert out == "[llm:paragraph]"


# --- FakePromptRepo + FakeGlossaryRepo --------------------------------------


async def test_fake_prompt_repo_returns_seeded_template() -> None:
    repo = FakePromptRepo(templates={"sys_en": "You are a translator."})
    assert await repo.load("sys_en") == "You are a translator."


async def test_fake_prompt_repo_raises_key_error_unknown() -> None:
    repo = FakePromptRepo()
    with pytest.raises(KeyError):
        await repo.load("missing")


async def test_fake_glossary_repo_returns_seeded_glossary() -> None:
    repo = FakeGlossaryRepo(glossary={"foo": "bar"})
    assert await repo.load(None) == {"foo": "bar"}


# --- InMemoryDraftStorage ---------------------------------------------------


async def test_in_memory_storage_save_returns_path() -> None:
    storage = InMemoryDraftStorage()
    when = datetime.datetime(2026, 5, 3, 12, 0, 0)
    path = await storage.save_draft("puey", "wikitext", "review", when)
    assert isinstance(path, Path)
    assert path == Path("/inmemory/2026-05-03/puey")


async def test_in_memory_storage_list_empty() -> None:
    storage = InMemoryDraftStorage()
    assert await storage.list_drafts() == []


async def test_in_memory_storage_list_after_save() -> None:
    storage = InMemoryDraftStorage()
    when = datetime.datetime(2026, 5, 3, 12, 0, 0)
    await storage.save_draft("puey", "w", "r", when)
    drafts = await storage.list_drafts()
    assert len(drafts) == 1
    assert drafts[0] == DraftMetadata(
        slug="puey",
        when=datetime.date(2026, 5, 3),
        dir=Path("/inmemory/2026-05-03/puey"),
    )


async def test_in_memory_storage_list_since_filter() -> None:
    storage = InMemoryDraftStorage()
    await storage.save_draft("old", "w", "r", datetime.datetime(2026, 5, 1, 0, 0))
    await storage.save_draft("new", "w", "r", datetime.datetime(2026, 5, 3, 0, 0))
    cutoff = datetime.datetime(2026, 5, 2, 0, 0)
    drafts = await storage.list_drafts(since=cutoff)
    assert [d.slug for d in drafts] == ["new"]


# --- Protocol satisfaction --------------------------------------------------


def test_fakes_satisfy_protocols() -> None:
    assert isinstance(FakeWikipediaReader(), WikipediaReader)
    assert isinstance(FakeWikidataReader(), WikidataReader)
    assert isinstance(FakeMachineTranslator(), MachineTranslator)
    assert isinstance(FakeLLMTranslator(), LLMTranslator)
    assert isinstance(FakePromptRepo(), PromptTemplateRepository)
    assert isinstance(FakeGlossaryRepo(), GlossaryRepository)
    assert isinstance(InMemoryDraftStorage(), DraftStorage)
    assert isinstance(FakeTransliterationValidator(), TransliterationValidator)


# --- DTO immutability ------------------------------------------------------


def test_dto_draft_metadata_immutable() -> None:
    meta = DraftMetadata(slug="x", when=datetime.date(2026, 5, 3), dir=Path("/inmemory"))
    with pytest.raises(dataclasses.FrozenInstanceError):
        meta.slug = "y"  # type: ignore[misc]


# --- adapters fixture wiring ------------------------------------------------


def test_adapters_fixture_returns_dict(adapters: dict[str, Any]) -> None:
    assert set(adapters.keys()) == {
        "wikipedia",
        "wikidata",
        "machine",
        "llm",
        "prompt_repo",
        "glossary_repo",
        "storage",
    }
