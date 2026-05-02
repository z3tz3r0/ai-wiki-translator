"""Pure wikitext transformations: comments, references, block splitting."""

from __future__ import annotations

import re

# Bug-fix vs legacy: legacy pattern `r"<!--[^>]*>"` closes on the first `>`
# inside a comment. Use the standard non-greedy `.*?-->` with re.DOTALL so
# multi-line comments and `>` characters inside comment bodies are handled.
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)

# Ports legacy `wikipedia_client.py:_strip_reference_tags` regex verbatim.
# Matches both `<ref>body</ref>` and self-closing `<ref name='x' />`.
_REF_TAG_RE = re.compile(r"<ref(?:[^>]*)?>(?:[^<]*</ref>)?")

# `[N]` placeholders inserted by strip_references.
_REF_PLACEHOLDER_RE = re.compile(r"\[(\d+)\]")

# Ports legacy `wikipedia_client.py:convert_to_list` regex verbatim.
_BLOCK_RE = re.compile(
    r"^.*\n*(?:\s?\|.*|\*\s*\[*.*\n?|\s?\}.*|\{\|.*|!.*|\(.*)*\s*\n*",
    re.MULTILINE,
)


def remove_comments(wikitext: str) -> str:
    """Strip HTML/wiki comments from wikitext."""
    return _COMMENT_RE.sub("", wikitext)


def strip_references(wikitext: str) -> tuple[str, dict[str, str]]:
    """Replace `<ref>...</ref>` (and self-closing) with `[1]`, `[2]`, ...

    Returns (cleaned_text, ref_map) where keys are the bracketed placeholders
    and values are the original `<ref>` strings, in order of appearance.
    """
    ref_map: dict[str, str] = {}
    counter = 0

    def _replace(match: re.Match[str]) -> str:
        nonlocal counter
        counter += 1
        placeholder = f"[{counter}]"
        ref_map[placeholder] = match.group(0)
        return placeholder

    return _REF_TAG_RE.sub(_replace, wikitext), ref_map


def restore_references(text: str, ref_map: dict[str, str]) -> str:
    """Inverse of `strip_references`. Unknown placeholders pass through."""

    def _replace(match: re.Match[str]) -> str:
        placeholder = match.group(0)
        return ref_map.get(placeholder, placeholder)

    return _REF_PLACEHOLDER_RE.sub(_replace, text)


def split_into_blocks(wikitext: str) -> list[str]:
    """Split wikitext into significant blocks, preserving table-like spans."""
    matches = _BLOCK_RE.findall(wikitext)
    return [m.strip() for m in matches if m.strip()]
