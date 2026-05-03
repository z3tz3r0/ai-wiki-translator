"""`summarize_diff` · unified diff between current th.wiki text and proposal."""

from __future__ import annotations

import difflib

from app.application.dto import ReviewNotes, SourceScore, ValidationResult


def summarize_diff(
    source_lang: str,
    source_score: SourceScore,
    validation: ValidationResult,
    current_th_wikitext: str,
    proposed_wikitext: str,
) -> ReviewNotes:
    """Wrap metadata + a markdown diff block in a `ReviewNotes` dataclass.

    The diff body is one of:
      * `(new article)` if `current_th_wikitext` is blank/whitespace
      * `(no changes)` if `current_th_wikitext == proposed_wikitext`
      * a fenced ```diff block (unified diff) otherwise

    The reviewer reads this in `<slug>.review.md` before pasting wikitext
    into th.wiki. Whitespace-only current text counts as "new" because a
    page that exists with only template scaffolding is effectively empty.
    """
    return ReviewNotes(
        source_lang=source_lang,
        source_score=source_score,
        validation=validation,
        diff_summary=_render_diff(current_th_wikitext, proposed_wikitext),
    )


def _render_diff(current: str, proposed: str) -> str:
    if not current.strip():
        return "(new article)"
    if current == proposed:
        return "(no changes)"
    diff_lines = difflib.unified_diff(
        current.splitlines(keepends=False),
        proposed.splitlines(keepends=False),
        fromfile="current",
        tofile="proposed",
        lineterm="",
    )
    body = "\n".join(diff_lines)
    return f"```diff\n{body}\n```"
