"""TranslateArticleUseCase · the Phase 3 orchestrator.

Pipeline:
    fetch th article (for diff)
        -> fetch langlinks
        -> pick source language (override · locale · fallback_en · first_langlink)
        -> fetch source article
        -> quality gate
        -> load glossary + system prompt
        -> translate per section type (machine for IMAGE/QUOTE/BULLET, LLM for TEXT)
        -> restore references
        -> diff against current th wikitext
        -> save draft via DraftStorage
        -> return Draft
"""

from __future__ import annotations

import dataclasses
import logging
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.application.dto import (
    Draft,
    ReviewNotes,
    SourceScore,
    TranslateArticleCommand,
    ValidationResult,
)
from app.application.ports import (
    DraftStorage,
    GlossaryRepository,
    LLMTranslator,
    MachineTranslator,
    PromptTemplateRepository,
    WikidataReader,
    WikipediaReader,
)
from app.application.services.diff_summary import summarize_diff
from app.application.services.quality_gate import QualityGate, is_acceptable_source
from app.application.services.source_picker import pick_best_source_language
from app.domain.classification import classify_section
from app.domain.entities import Article
from app.domain.merge import merge_dictionaries
from app.domain.references import restore_references, split_into_blocks
from app.domain.text_transforms import (
    replace_bullet_point,
    replace_image_description,
    replace_quote,
    replace_with_dictionary,
)
from app.domain.values import Dictionary, SectionType

logger = logging.getLogger(__name__)


def _utcnow_naive() -> datetime:
    """Return a naive UTC datetime · matches DraftStorage convention."""
    return datetime.now(UTC).replace(tzinfo=None)


def _slugify(title: str) -> str:
    """Filename-safe slug.

    Rules:
      * spaces collapse to ``-``
      * ASCII letters/digits lowercase
      * non-ASCII letters preserved as-is
      * Unicode ``Mn`` (non-spacing combining marks · Thai vowels and tone
        marks, Vietnamese diacritics, etc.) preserved so that visually-distinct
        titles keep distinct slugs · stripping them collides e.g. ``ปรัชญา``
        and ``ปรชญา`` to the same directory.
    """
    out: list[str] = []
    for ch in title:
        if ch.isspace():
            out.append("-")
        elif ch.isalnum() or unicodedata.category(ch).startswith("M"):
            out.append(ch.lower() if ch.isascii() else ch)
        elif ch in "-_":
            out.append(ch)
    slug = "".join(out).strip("-")
    return slug or "untitled"


_PASSTHROUGH_TYPES: frozenset[SectionType] = frozenset(
    {
        SectionType.EMPTY,
        SectionType.GLOSSARY,
        SectionType.CATEGORY,
        SectionType.TEMPLATE,
        SectionType.SECTION_HEADER,
    }
)


@dataclass(frozen=True)
class TranslateArticleUseCase:
    wikipedia: WikipediaReader
    wikidata: WikidataReader
    machine: MachineTranslator
    llm: LLMTranslator
    prompt_repo: PromptTemplateRepository
    glossary_repo: GlossaryRepository
    storage: DraftStorage
    quality_gate: QualityGate = field(default_factory=QualityGate)
    target_lang: str = "th"
    locale_to_lang: dict[str, str] = field(default_factory=dict)
    prompt_template_id: str = "system_instruction_th"
    clock: Callable[[], datetime] = _utcnow_naive

    async def execute(self, cmd: TranslateArticleCommand) -> Draft:
        slug = _slugify(cmd.title)
        logger.info("translating %r (slug=%s, target=%s)", cmd.title, slug, self.target_lang)

        th_article = await self.wikipedia.fetch_article(cmd.title, self.target_lang)
        current_th_wikitext = th_article.wikitext if th_article else ""

        langlinks = await self.wikipedia.fetch_langlinks(cmd.title, self.target_lang)
        logger.info("found %d langlinks for %r", len(langlinks), cmd.title)

        try:
            source_lang, source_score = await self._pick_source(cmd, langlinks)
        except ValueError as exc:
            logger.warning("source pick failed: %s", exc)
            return await self._save_rejection(
                slug=slug,
                source_lang="",
                source_score=_placeholder_score(""),
                validation=ValidationResult(passed=False, reasons=(str(exc),)),
            )
        logger.info("picked source=%s via %s", source_lang, source_score.winning_signal)

        source_title = langlinks.get(source_lang, cmd.title)
        source_article = await self.wikipedia.fetch_article(source_title, source_lang)
        if source_article is None:
            reason = f"source article {source_title!r} not found in {source_lang!r}"
            logger.warning(reason)
            return await self._save_rejection(
                slug=slug,
                source_lang=source_lang,
                source_score=source_score,
                validation=ValidationResult(passed=False, reasons=(reason,)),
            )

        source_score = dataclasses.replace(
            source_score,
            word_count=len(source_article.wikitext_no_ref.split()),
            ref_count=len(source_article.ref_map),
        )
        logger.info(
            "source loaded: words=%d refs=%d",
            source_score.word_count,
            source_score.ref_count,
        )

        validation = is_acceptable_source(source_article, self.quality_gate)
        if not validation.passed:
            logger.warning("quality gate rejected source: %s", "; ".join(validation.reasons))
            return await self._save_rejection(
                slug=slug,
                source_lang=source_lang,
                source_score=source_score,
                validation=validation,
            )
        logger.info("quality gate passed")

        glossary = await self.glossary_repo.load(cmd.glossary_path)
        system_instruction = await self.prompt_repo.load(self.prompt_template_id)
        dictionary = merge_dictionaries(glossary, source_article.dictionary)
        logger.info("loaded glossary=%d terms, dictionary=%d terms", len(glossary), len(dictionary))

        proposed = await self._translate_article(
            source_article=source_article,
            base_dictionary=dictionary,
            source_lang=source_lang,
            system_instruction=system_instruction,
        )

        review_notes = summarize_diff(
            source_lang=source_lang,
            source_score=source_score,
            validation=validation,
            current_th_wikitext=current_th_wikitext,
            proposed_wikitext=proposed,
        )
        review_md = _render_review_md(review_notes, rejected=False)

        await self.storage.save_draft(
            slug=slug,
            wikitext=proposed,
            review_md=review_md,
            when=self.clock(),
        )
        return Draft(
            slug=slug,
            source_lang=source_lang,
            source_score=source_score,
            validation=validation,
            wikitext=proposed,
            review_md=review_md,
        )

    async def _pick_source(
        self,
        cmd: TranslateArticleCommand,
        langlinks: dict[str, str],
    ) -> tuple[str, SourceScore]:
        if cmd.source_lang_override:
            if cmd.source_lang_override not in langlinks:
                raise ValueError(
                    f"langlink {cmd.source_lang_override!r} not available for {cmd.title!r}"
                )
            return cmd.source_lang_override, SourceScore(
                lang=cmd.source_lang_override,
                word_count=0,
                ref_count=0,
                locale_match=False,
                winning_signal="override",
            )
        if not langlinks:
            raise ValueError(
                f"article {cmd.title!r} has no langlinks · no source language available"
            )
        qid = await self.wikidata.resolve_qid(cmd.title, self.target_lang)
        claims = await self.wikidata.fetch_claims(qid) if qid else {}
        return pick_best_source_language(
            langlinks=langlinks,
            claims=claims,
            locale_to_lang=self.locale_to_lang,
        )

    async def _translate_article(
        self,
        *,
        source_article: Article,
        base_dictionary: Dictionary,
        source_lang: str,
        system_instruction: str,
    ) -> str:
        unknown_links = [w for w in source_article.wikilinks if w not in base_dictionary]
        if unknown_links:
            logger.info(
                "translating %d unknown wikilinks via machine translator",
                len(unknown_links),
            )
            translations = await self.machine.translate_batch(
                unknown_links, source_lang, self.target_lang
            )
            base_dictionary = {
                **base_dictionary,
                **dict(zip(unknown_links, translations, strict=True)),
            }

        def lookup(text: str) -> str:
            return base_dictionary.get(text, text)

        blocks = split_into_blocks(source_article.wikitext_no_ref)
        total = len(blocks)
        logger.info("split into %d sections", total)
        translated: list[str] = []
        for index, block in enumerate(blocks, start=1):
            section_type = classify_section(block, source_article.dictionary)
            logger.info("[%d/%d] type=%s", index, total, section_type.name)
            if section_type in _PASSTHROUGH_TYPES:
                translated.append(block)
            elif section_type is SectionType.IMAGE:
                translated.append(replace_image_description(block, base_dictionary, lookup))
            elif section_type is SectionType.QUOTE:
                translated.append(replace_quote(block, base_dictionary, lookup))
            elif section_type is SectionType.BULLET_POINT:
                translated.append(replace_bullet_point(block, base_dictionary, lookup))
            else:
                with_dict = replace_with_dictionary(block, base_dictionary, lookup)
                translated.append(await self.llm.translate_section(with_dict, system_instruction))

        joined = "\n\n".join(translated)
        logger.info("all sections translated; restoring %d refs", len(source_article.ref_map))
        return restore_references(joined, source_article.ref_map)

    async def _save_rejection(
        self,
        *,
        slug: str,
        source_lang: str,
        source_score: SourceScore,
        validation: ValidationResult,
    ) -> Draft:
        """Build a rejection draft, persist it, and return it.

        The diff body is intentionally elided here · no proposal was
        produced, so a unified diff against an empty string would either
        report ``(new article)`` (misleading: nothing was actually drafted)
        or every line of current th wikitext as a deletion (also misleading:
        nothing is being deleted). Reviewer sees the rejection reasons
        in the Quality Gate section instead.
        """
        notes = ReviewNotes(
            source_lang=source_lang,
            source_score=source_score,
            validation=validation,
            diff_summary="(rejected · no proposal generated)",
        )
        review_md = _render_review_md(notes, rejected=True)
        await self.storage.save_draft(
            slug=slug,
            wikitext="",
            review_md=review_md,
            when=self.clock(),
        )
        return Draft(
            slug=slug,
            source_lang=source_lang,
            source_score=source_score,
            validation=validation,
            wikitext="",
            review_md=review_md,
        )


def _placeholder_score(lang: str) -> SourceScore:
    """SourceScore stand-in for paths that fail before the picker chooses."""
    return SourceScore(
        lang=lang,
        word_count=0,
        ref_count=0,
        locale_match=False,
        winning_signal="error",
    )


def _render_review_md(notes: ReviewNotes, *, rejected: bool) -> str:
    """Render the markdown body the reviewer reads before pasting wikitext."""
    lines: list[str] = []
    lines.append(f"# Translation Draft Review · {notes.source_lang or '(no source)'}")
    lines.append("")
    lines.append("## Source")
    lines.append(f"- **language**: `{notes.source_lang}`")
    lines.append(f"- **word_count**: {notes.source_score.word_count}")
    lines.append(f"- **ref_count**: {notes.source_score.ref_count}")
    lines.append(f"- **picker_signal**: `{notes.source_score.winning_signal}`")
    lines.append(f"- **locale_match**: {notes.source_score.locale_match}")
    lines.append("")
    lines.append("## Quality Gate")
    if notes.validation.passed:
        lines.append("- **status**: passed")
    else:
        status_label = "rejected" if rejected else "failed"
        lines.append(f"- **status**: {status_label}")
        lines.append("- **reasons**:")
        for reason in notes.validation.reasons:
            lines.append(f"  - {reason}")
    lines.append("")
    lines.append("## Diff")
    lines.append(notes.diff_summary)
    lines.append("")
    return "\n".join(lines)
