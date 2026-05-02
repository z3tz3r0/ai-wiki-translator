"""Section classification: label a wikitext block + derive its execution mode."""

from __future__ import annotations

import re

from app.domain.values import ExecutionMode, Glossary, SectionType

# Bug-fix vs legacy: legacy lookahead `(?=\n)` only matched if a `\n` followed
# the closing `]]`. Stripped blocks (no trailing newline) silently fell through
# to TEXT. Fix: accept either `\n` or end-of-string.
_IMAGE_RE = re.compile(r"\[{2}File:.*?\|*[^\]]*\]{2}(?=\n|$)")

# Ports legacy regexes verbatim.
_QUOTE_RE = re.compile(r"\{\{(?:blockquote|quote)\|.*\}\}", re.DOTALL)
_BULLET_RE = re.compile(
    r"^[•\*]+\s*(?:\[{1,2}|\{*).*(?:\]{1,2}|\}*)",
    re.MULTILINE,
)
_CATEGORY_RE = re.compile(r"\[\[[Cc]ategory:.*\]\]", re.MULTILINE)


def classify_section(block: str, glossary: Glossary) -> SectionType:
    """Classify a wikitext block. Mirrors legacy `_determine_section_type` order."""
    if block in glossary:
        return SectionType.GLOSSARY
    if not block:
        return SectionType.EMPTY
    if block.startswith("==") and block.endswith("=="):
        return SectionType.SECTION_HEADER
    if _IMAGE_RE.match(block):
        return SectionType.IMAGE
    if _QUOTE_RE.match(block):
        return SectionType.QUOTE
    if _BULLET_RE.match(block):
        return SectionType.BULLET_POINT
    if _CATEGORY_RE.match(block):
        return SectionType.CATEGORY
    if (block.startswith("{{") and block.endswith("}}")) or (
        block.startswith("[[") and block.endswith("]]")
    ):
        return SectionType.TEMPLATE
    return SectionType.TEXT


def execution_mode_for(section_type: SectionType) -> ExecutionMode:
    """TEXT sections run FIFO through the LLM; everything else can run async."""
    if section_type is SectionType.TEXT:
        return ExecutionMode.FIFO
    return ExecutionMode.ASYNC
