"""High-level orchestration for Wikipedia translation."""

from __future__ import annotations

import asyncio
import re
from typing import Callable, Dict, Iterable, List

from app.models.translation_request import TranslationRequest
from app.models.wiki_section import WikiSection
from app.services.assistant_service import GenerativeAssistantService
from app.services.glossary_service import GlossaryService
from app.services.google_translation import GoogleTranslationService
from app.services.prompt_builder import PromptBuilder
from app.services.wikipedia_client import WikipediaClient, WikipediaPage
from app.utils.text_processing import (
    remove_comments,
    replace_bullet_point,
    replace_image_description,
    replace_quote,
    replace_with_dictionary,
)


class WikiTranslationService:
    """Coordinates the multiple services required to translate an article."""

    def __init__(
        self,
        *,
        wikipedia_client: WikipediaClient | None = None,
        glossary_service: GlossaryService | None = None,
        translation_service: GoogleTranslationService | None = None,
        prompt_builder: PromptBuilder | None = None,
        assistant_factory: Callable[[str], GenerativeAssistantService] | None = None,
        prompt_template: str = "app/prompts/system_instruction_en.md",
        rate_limit_delay: float = 6.0,
    ) -> None:
        self.wikipedia_client = wikipedia_client or WikipediaClient()
        self.glossary_service = glossary_service or GlossaryService()
        self.translation_service = translation_service or GoogleTranslationService()
        self.prompt_template = (
            prompt_builder.template_path if prompt_builder else prompt_template
        )
        self.prompt_builder = prompt_builder or PromptBuilder(self.prompt_template)
        self.assistant_factory = assistant_factory or (
            lambda prompt: GenerativeAssistantService(prompt)
        )
        self.rate_limit_delay = rate_limit_delay

    async def translate(self, request: TranslationRequest) -> str:
        page = self.wikipedia_client.fetch_page(request.title_name)
        glossary = self.glossary_service.load(request.glossary_path)
        dictionary = self.translation_service.enrich_title_dictionary(
            page.missing_translations,
            page.dictionary,
        )
        cleaned_wikitext = remove_comments(page.wikitext_no_ref)
        blocks = WikipediaPage.convert_to_list(cleaned_wikitext)
        sections = self._preprocess_wikitext(blocks, glossary)

        system_instruction = self.prompt_builder.build(
            title_name=request.title_name,
            th_title_name=request.thai_title_name,
            dictionary=dictionary,
        )
        assistant = self.assistant_factory(system_instruction)
        translations = await self._process_sections(sections, glossary, dictionary, assistant)
        final_text = "\n".join(translations)
        return page.replace_references(final_text)

    def _preprocess_wikitext(
        self, blocks: Iterable[str], glossary: Dict[str, str]
    ) -> List[WikiSection]:
        processed: List[WikiSection] = []
        for index, block in enumerate(blocks, start=1):
            section_type = self._determine_section_type(block, glossary)
            mode = "ASYNC" if section_type != "text" else "FIFO"
            processed.append(
                WikiSection(task_id=index, content=block, type=section_type, mode=mode)
            )
        return processed

    def _determine_section_type(self, block: str, glossary: Dict[str, str]) -> str:
        if block in glossary:
            return "glossary"
        if not block:
            return "empty"
        if block.startswith("==") and block.endswith("=="):
            return "section_header"
        if self._is_image(block):
            return "image"
        if self._is_quote(block):
            return "quote"
        if self._is_bullet_point(block):
            return "bullet_point"
        if self._is_category(block):
            return "category"
        if self._is_template(block):
            return "template"
        return "text"

    @staticmethod
    def _is_image(block: str) -> bool:
        return re.match(r"\[{2}File:.*?\|*[^\]]*\]{2}(?=\n)", block) is not None

    @staticmethod
    def _is_quote(block: str) -> bool:
        return re.match(r"\{\{(?:blockquote|quote)\|.*\}\}", block, flags=re.DOTALL) is not None

    @staticmethod
    def _is_template(block: str) -> bool:
        return (block.startswith("{{") and block.endswith("}}")) or (
            block.startswith("[[") and block.endswith("]]"))

    @staticmethod
    def _is_bullet_point(block: str) -> bool:
        return re.match(r"^[•\*]{1,}\s*(?:\[{1,2}|\{*).*(?:\]{1,2}|\}*)", block, flags=re.MULTILINE) is not None

    @staticmethod
    def _is_category(block: str) -> bool:
        return re.match(r"\[\[[Cc]ategory:.*\]\]", block, flags=re.MULTILINE) is not None

    async def _process_sections(
        self,
        sections: Iterable[WikiSection],
        glossary: Dict[str, str],
        dictionary: Dict[str, str],
        assistant: GenerativeAssistantService,
    ) -> List[str]:
        async_sections = [s for s in sections if s.mode == "ASYNC"]
        fifo_sections = [s for s in sections if s.mode == "FIFO"]

        async_tasks = {
            section.task_id: self._process_section(section, glossary, dictionary, assistant)
            for section in async_sections
        }
        fifo_results: Dict[int, str] = {}
        for section in fifo_sections:
            fifo_results[section.task_id] = await self._process_section(
                section, glossary, dictionary, assistant
            )

        async_results = await asyncio.gather(*async_tasks.values()) if async_tasks else []
        async_results_dict = dict(zip(async_tasks.keys(), async_results))

        ordered_results: List[str] = []
        for section in sections:
            if section.mode == "ASYNC":
                ordered_results.append(async_results_dict[section.task_id])
            else:
                ordered_results.append(fifo_results[section.task_id])
        return ordered_results

    async def _process_section(
        self,
        section: WikiSection,
        glossary: Dict[str, str],
        dictionary: Dict[str, str],
        assistant: GenerativeAssistantService,
    ) -> str:
        translate = lambda text: self.translation_service.translate_text(text) if text else text

        if section.type == "glossary":
            return glossary.get(section.content, "")
        if section.type == "empty":
            return ""
        if section.type == "section_header":
            return self.translation_service.translate_text(section.content)
        if section.type == "image":
            return replace_image_description(section.content, dictionary, translate)
        if section.type == "quote":
            return replace_quote(section.content, dictionary, translate)
        if section.type == "bullet_point":
            return replace_bullet_point(section.content, dictionary, translate)
        if section.type == "category":
            return replace_with_dictionary(section.content, dictionary, translate)
        if section.type == "template":
            return section.content

        await asyncio.sleep(self.rate_limit_delay)
        response = await asyncio.to_thread(assistant.send_message, section.content)
        return response

