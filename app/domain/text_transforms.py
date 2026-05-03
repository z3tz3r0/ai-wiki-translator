"""Pure wikitext transformations and glossary line parsing."""

from __future__ import annotations

import re
from collections.abc import Callable

from app.domain.values import Dictionary, Glossary

_WIKILINK_RE = re.compile(r"\[\[(?!File:)(?:([^#|\]]+)(?:#[^|\]]*)?(?:\|([^\]]+))?)\]\]")
# Bug-fix vs legacy: legacy `(?=\n)` lookahead rejected last-line images, and
# the redundant 3-way alternation `(.*|\n*?|[^\]]*)` always took the greedy `.*`
# branch (DOTALL not set). Simplify to a single greedy group with `(?=\n|$)`.
_IMAGE_DESC_RE = re.compile(r"\[{2}File:.*?(?:\|.*\|)(.*)\]{2}(?=\n|$)")
_QUOTE_CONTENT_RE = re.compile(r"\{\{(?:blockquote|quote)\|(.*)\}\}", re.DOTALL)
_BULLET_CONTENT_RE = re.compile(r"^[•\*]+\s*(.*)")


def _replace_group(text: str, match: re.Match[str], group: int, replacement: str) -> str:
    """Splice `replacement` into `text` at the span of capture `group` in `match`.

    Avoids the bug where `text.replace(match.group(N), replacement)` would
    replace every occurrence of the captured substring, not just the matched
    span. Use this when the captured text could appear elsewhere in `text`.
    """
    start, end = match.span(group)
    return f"{text[:start]}{replacement}{text[end:]}"


def parse_glossary_lines(lines: list[str]) -> Glossary:
    """Parse glossary text lines in `term:translation` format.

    Lines without `:` are skipped silently. Whitespace around term and
    translation is stripped. Lines whose term is empty after stripping
    (e.g. `:value` or `   :value`) are also skipped.
    """
    glossary: Glossary = {}
    for line in lines:
        if ":" not in line:
            continue
        term, translation = line.strip().split(":", 1)
        term = term.strip()
        if not term:
            continue
        glossary[term] = translation.strip()
    return glossary


def replace_with_dictionary(
    text: str,
    dictionary: Dictionary,
    translate: Callable[[str], str],
) -> str:
    """Translate `[[wikilinks]]` using the dictionary, falling back to translate().

    Each wikilink is rewritten atomically via `re.sub`, avoiding the legacy
    bug where `str.replace` over an accumulating buffer would collide on
    prefix-overlapping link names (e.g. `Alpha` corrupting `AlphaGo`).
    """

    def _rewrite(match: re.Match[str]) -> str:
        original_link = match.group(1)
        display = match.group(2)
        replacement = dictionary.get(original_link)
        translated_link = replacement if replacement else translate(original_link)
        if display is None:
            return f"[[{translated_link}]]"
        if display == original_link:
            return f"[[{translated_link}|{translated_link}]]"
        return f"[[{translated_link}|{translate(display)}]]"

    return _WIKILINK_RE.sub(_rewrite, text)


def replace_image_description(
    text: str,
    dictionary: Dictionary,
    translate: Callable[[str], str],
) -> str:
    """Translate the description portion of a `[[File:...|...|description]]` block."""
    match = _IMAGE_DESC_RE.search(text)
    if not match:
        return text
    description = match.group(1)
    translated = translate(replace_with_dictionary(description, dictionary, translate))
    return _replace_group(text, match, 1, translated).replace("File:", "ไฟล์:", 1)


def replace_quote(
    text: str,
    dictionary: Dictionary,
    translate: Callable[[str], str],
) -> str:
    """Translate the inner content of a `{{blockquote|...}}` or `{{quote|...}}` block."""
    match = _QUOTE_CONTENT_RE.search(text)
    if not match:
        return text
    content = match.group(1)
    translated = translate(replace_with_dictionary(content, dictionary, translate))
    return _replace_group(text, match, 1, translated)


def replace_bullet_point(
    text: str,
    dictionary: Dictionary,
    translate: Callable[[str], str],
) -> str:
    """Translate the post-bullet content while preserving the marker."""
    match = _BULLET_CONTENT_RE.search(text)
    if not match:
        return text
    content = match.group(1)
    translated = translate(replace_with_dictionary(content, dictionary, translate))
    return _replace_group(text, match, 1, translated)
