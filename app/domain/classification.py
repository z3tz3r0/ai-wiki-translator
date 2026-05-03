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

# Single-line `{{name|value}}` templates carry translatable prose (e.g.
# `{{Short description|Thai economist (1916-1999)}}`, `{{efn|footnote text}}`).
# Routing them to TEXT lets the LLM translate the value; the existing TEMPLATE
# rule passthroughs raw English. Excluding `=` skips key=value structural
# templates (`{{Infobox person|name=x}}`, `{{cite news|title=Foo}}`) which
# would mangle as prose; excluding nested `{{` skips composite templates.
_VALUED_TEMPLATE_RE = re.compile(r"^\{\{[^{}=\n]*\|[^{}=\n]*\}\}$")

# Lines like `| param = value` mark template parameters. Blocks containing them
# are either closed multi-line templates (cite/infobox) or orphan tails from
# `references.py` block tearing (e.g. `*[[Peter]]}}\n| profession = Economist`,
# currently misclassified as BULLET_POINT → dict-sub). Routing to TEXT lets the
# LLM translate the values, recovering chrF that passthrough/dict-sub miss.
# Single-line `{{Infobox person|name=x}}` has no line-start `|` so the frozen
# TEMPLATE test still passes through the existing branch below.
_TEMPLATE_PARAMS_RE = re.compile(r"^\s*\|\s*\w+\s*=", re.MULTILINE)


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
    if _TEMPLATE_PARAMS_RE.search(block):
        return SectionType.TEXT
    if _BULLET_RE.match(block):
        return SectionType.BULLET_POINT
    if _CATEGORY_RE.match(block):
        return SectionType.CATEGORY
    if _VALUED_TEMPLATE_RE.match(block):
        return SectionType.TEXT
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
