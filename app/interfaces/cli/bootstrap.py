"""DI wiring · build use cases with real Phase-4 adapters.

Heavy SDK imports (google-genai) are deferred to call time so the CLI can
render ``--help`` or run tests with monkeypatched factories without
hitting ``os.environ["GEMINI_API_KEY"]``.

Term-batch translation uses the free Wikimedia MinT service (no auth,
no billing) so this tool stays usable for volunteer translators. Gemini
is reserved for the heavier section-level translation work where its
context awareness matters.
"""

from __future__ import annotations

import os
from pathlib import Path

from app.application.use_cases.list_drafts import ListDraftsUseCase
from app.application.use_cases.translate_article import TranslateArticleUseCase
from app.infrastructure.file_glossary_repo import FileGlossaryRepository
from app.infrastructure.file_prompt_repo import FilePromptRepository
from app.infrastructure.gemini_genai import GeminiAssistantAdapter
from app.infrastructure.markdown_draft_storage import MarkdownDraftStorage
from app.infrastructure.wikidata_http import WikidataHttpReader
from app.infrastructure.wikimedia_mint import WikimediaMinTAdapter
from app.infrastructure.wikipedia_http import DEFAULT_USER_AGENT, WikipediaHttpReader


def _resolve_prompts_dir() -> Path:
    env = os.environ.get("WIKI_TRANSLATOR_PROMPTS_DIR")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent.parent / "prompts"


def _resolve_output_dir(override: Path | None) -> Path:
    if override is not None:
        return override
    env = os.environ.get("WIKI_TRANSLATOR_OUTPUT_DIR")
    if env:
        return Path(env)
    return MarkdownDraftStorage.default_user_dir()


def build_translate_use_case(*, output_dir: Path | None = None) -> TranslateArticleUseCase:
    """Wire `TranslateArticleUseCase` with the real adapters.

    Reads required credentials from the environment lazily · raises
    ``RuntimeError`` with a clear message if a required key is missing.
    """
    from google import genai

    user_agent = os.environ.get("WIKI_TRANSLATOR_USER_AGENT", DEFAULT_USER_AGENT)
    wikipedia = WikipediaHttpReader(user_agent=user_agent)
    wikidata = WikidataHttpReader(user_agent=user_agent)
    machine = WikimediaMinTAdapter(user_agent=user_agent)

    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is required · export it before running `wiki-translate`")
    gemini_model = os.environ.get("WIKI_TRANSLATOR_GEMINI_MODEL", "gemini-2.0-flash")
    llm = GeminiAssistantAdapter(client=genai.Client(api_key=gemini_api_key), model=gemini_model)

    return TranslateArticleUseCase(
        wikipedia=wikipedia,
        wikidata=wikidata,
        machine=machine,
        llm=llm,
        prompt_repo=FilePromptRepository(prompts_dir=_resolve_prompts_dir()),
        glossary_repo=FileGlossaryRepository(),
        storage=MarkdownDraftStorage(base_dir=_resolve_output_dir(output_dir)),
    )


def build_list_drafts_use_case(*, output_dir: Path | None = None) -> ListDraftsUseCase:
    """Wire `ListDraftsUseCase` with the on-disk draft store."""
    return ListDraftsUseCase(storage=MarkdownDraftStorage(base_dir=_resolve_output_dir(output_dir)))
