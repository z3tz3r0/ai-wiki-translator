"""Pure wikitext transformations: comments, references, block splitting."""

from __future__ import annotations

import re
from collections.abc import Mapping

# Bug-fix vs legacy: legacy pattern `r"<!--[^>]*>"` closes on the first `>`
# inside a comment. Use the standard non-greedy `.*?-->` with re.DOTALL so
# multi-line comments and `>` characters inside comment bodies are handled.
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)

# Matches both `<ref>body</ref>` (with possibly nested tags inside body) and
# self-closing `<ref name='x' />`. The body uses `.*?` with re.DOTALL so
# nested HTML/wikitext like <cite>...</cite> inside the ref is consumed
# fully · the legacy `[^<]*` pattern dropped on the first nested `<`.
_REF_TAG_RE = re.compile(r"<ref(?:[^>]*?)(?:/>|>.*?</ref>)", re.DOTALL)

# `[[REF_n]]` markers inserted by strip_references. The translation prompt
# (app/prompts/system_instruction_th.md) and the self-consistency scorer use the
# same form, so the LLM keeps exactly what restore looks for. Spacing variants an
# LLM may produce ("[[ REF_1 ]]", "[[REF 1]]") still map back. A bare "[12]" in
# article text is never touched: the old `[N]` placeholder turned it into a ref.
_REF_MARKER_RE = re.compile(r"\[\[\s*REF[_ ](\d+)\s*\]\]")
_REF_TARGET_RE = re.compile(r"\s*REF[_ ]\d+\s*")

# Ports legacy `wikipedia_client.py:convert_to_list` regex verbatim.
_BLOCK_RE = re.compile(
    r"^.*\n*(?:\s?\|.*|\*\s*\[*.*\n?|\s?\}.*|\{\|.*|!.*|\(.*)*\s*\n*",
    re.MULTILINE,
)


def remove_comments(wikitext: str) -> str:
    """Strip HTML/wiki comments from wikitext."""
    return _COMMENT_RE.sub("", wikitext)


def ref_marker(number: int) -> str:
    """The canonical marker for the ``number``-th reference."""
    return f"[[REF_{number}]]"


def strip_references(wikitext: str) -> tuple[str, dict[str, str]]:
    """Replace `<ref>...</ref>` (and self-closing) with `[[REF_1]]`, `[[REF_2]]`, ...

    Returns (cleaned_text, ref_map) where keys are the markers and values are
    the original `<ref>` strings, in order of appearance.
    """
    ref_map: dict[str, str] = {}
    counter = 0

    def _replace(match: re.Match[str]) -> str:
        nonlocal counter
        counter += 1
        placeholder = ref_marker(counter)
        ref_map[placeholder] = match.group(0)
        return placeholder

    return _REF_TAG_RE.sub(_replace, wikitext), ref_map


def restore_references(text: str, ref_map: Mapping[str, str]) -> str:
    """Inverse of `strip_references`. Unknown markers pass through unchanged."""

    def _replace(match: re.Match[str]) -> str:
        return ref_map.get(ref_marker(int(match.group(1))), match.group(0))

    return _REF_MARKER_RE.sub(_replace, text)


def count_ref_markers(text: str) -> int:
    """How many reference markers are still in ``text`` (unrestored refs)."""
    return len(_REF_MARKER_RE.findall(text))


def is_ref_marker(target: str) -> bool:
    """True when a wikilink target is really a reference marker (``REF_12``)."""
    return _REF_TARGET_RE.fullmatch(target) is not None


def split_into_blocks(wikitext: str) -> list[str]:
    """Split wikitext into significant blocks, preserving table-like spans."""
    matches = _BLOCK_RE.findall(wikitext)
    return [m.strip() for m in matches if m.strip()]
