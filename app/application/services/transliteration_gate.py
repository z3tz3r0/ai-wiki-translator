"""Transliteration quality gate · detect Thai-script candidates and judge them.

Two responsibilities split into module-level functions:

* ``detect_candidates(wikitext)`` finds Thai-script spans in the
  proposed wikitext that look like transliterations of foreign proper
  nouns. Conservative regex per PRD risk #5 · over-detect is fine,
  miss is not. Returns deduplicated candidates in source order.
* ``evaluate_transliterations(...)`` is the orchestrator · runs
  detection, calls the injected validator (one batched call), and
  wraps the result in ``TransliterationReport``. Soft-degrades to
  ``status=skipped`` when ``rules`` is ``None``.

Pure-application service · no IO except via the injected
``TransliterationValidator`` port.
"""

from __future__ import annotations

import logging
import re

from app.application.dto import (
    LanguageRuleSet,
    TransliterationCandidate,
    TransliterationReport,
    TransliterationVerdict,
)
from app.application.ports import TransliterationValidator

logger = logging.getLogger(__name__)

# Regex for one Thai-script "word" (contiguous Thai chars). The two
# detection regexes below both require at least 2 Thai words separated
# by ASCII spaces · single-word spans are too noisy (most native Thai
# vocabulary is single-word) and false-positive detections train the
# user to ignore the gate.
_THAI_WORD = r"[฀-๿]+"
# Wikilink with displayed text: [[Latin Target|Thai displayed]].
# Structurally cannot match `[[REF_N]]` markers · they have no `|`.
_WIKILINK_PIPE_RE = re.compile(
    rf"\[\[(?P<target>[^\]\|]+)\|(?P<displayed>{_THAI_WORD}(?:[ \t]+{_THAI_WORD})+)\]\]"
)
# Thai run followed by parenthetical Latin: "แอนเดอส์ เฮลส์เบิร์ก (Anders Hejlsberg)"
_THAI_THEN_LATIN_PAREN_RE = re.compile(
    rf"(?P<thai>{_THAI_WORD}(?:[ \t]+{_THAI_WORD})+)\s*\((?P<latin>[A-Za-z][A-Za-z .,'\-]+)\)"
)
# Surrounding context window for the LLM judge.
_CONTEXT_RADIUS = 80


def detect_candidates(wikitext: str) -> tuple[TransliterationCandidate, ...]:
    """Find candidate Thai-script transliterations in ``wikitext``.

    Strategy (conservative, over-detect):

    1. Scan for ``[[target|displayed]]`` wikilinks where ``displayed``
       is a multi-word Thai run · the Latin ``target`` is the hint.
    2. Scan for multi-word Thai runs immediately followed by a
       parenthetical Latin disclosure.
    3. Deduplicate by ``thai`` text · same name appearing twice in
       the article gets one verdict.

    Single-word Thai spans are NOT emitted in v1 · most native Thai
    vocabulary is single-word and false-positive detections train the
    user to ignore the gate. Phase 4 metrics inform whether to widen
    the regex or move to LLM-based detection.
    """
    seen: set[str] = set()
    candidates: list[TransliterationCandidate] = []

    def _emit(thai: str, latin_hint: str | None, span_start: int, span_end: int) -> None:
        if thai in seen:
            return
        seen.add(thai)
        ctx_start = max(0, span_start - _CONTEXT_RADIUS)
        ctx_end = min(len(wikitext), span_end + _CONTEXT_RADIUS)
        context = wikitext[ctx_start:ctx_end]
        candidates.append(
            TransliterationCandidate(
                thai=thai,
                context=context,
                latin_hint=latin_hint,
            )
        )

    for match in _WIKILINK_PIPE_RE.finditer(wikitext):
        displayed = match.group("displayed")
        target = match.group("target").strip()
        _emit(displayed, target or None, match.start(), match.end())

    # Greedy paren regex tends to absorb a native-Thai prefix verb / preposition
    # before the actual transliteration (e.g. "ถูกออกแบบโดย แอนเดอส์ เฮลส์เบิร์ก
    # (Anders Hejlsberg)" matches all three Thai words). Trim to the last two
    # words when the run is 3+ words long. Known limitation · genuine 3+ word
    # transliterations like "มาร์ติน ลูเธอร์ คิง" get clipped to the last two
    # words. Phase 4 metrics decide whether to widen this to 3+ or replace the
    # heuristic with smarter boundary detection.
    for match in _THAI_THEN_LATIN_PAREN_RE.finditer(wikitext):
        thai = match.group("thai")
        latin = match.group("latin").strip()
        span_start = match.start("thai")
        words = thai.split()
        if len(words) > 2:
            thai = " ".join(words[-2:])
            span_start += match.group("thai").rfind(thai)
        _emit(thai, latin or None, span_start, match.end())

    logger.info("detected %d transliteration candidate(s)", len(candidates))
    return tuple(candidates)


async def evaluate_transliterations(
    *,
    source_lang: str,
    proposed_wikitext: str,
    rules: LanguageRuleSet | None,
    validator: TransliterationValidator,
) -> TransliterationReport:
    """Orchestrate detection + validation, return a structured report.

    Soft-degrades to ``status=skipped`` when ``rules is None`` (the
    Phase 1 cache miss · loud banner per PRD). When candidates are
    found, calls the validator once with all of them and wraps the
    result.
    """
    if rules is None:
        reason = (
            f"no transliteration rules cached for source_lang={source_lang!r} · "
            f"run `wiki-refresh-rules --lang {source_lang}` to enable validation"
        )
        logger.warning("transliteration gate skipped: %s", reason)
        return TransliterationReport(
            source_lang=source_lang,
            candidates_found=0,
            verdicts=(),
            status="skipped",
            skipped_reason=reason,
        )

    candidates = detect_candidates(proposed_wikitext)
    if not candidates:
        logger.info("no transliteration candidates detected · gate trivially passes")
        return TransliterationReport(
            source_lang=source_lang,
            candidates_found=0,
            verdicts=(),
            status="ok",
        )

    verdicts = await validator.validate(candidates, rules)
    if len(verdicts) != len(candidates):
        # Contract violation · pad with uncertain so orchestrator stays
        # crash-free. Adapter SHOULD have padded itself; this is a
        # belt-and-suspenders guard.
        logger.warning(
            "validator returned %d verdicts for %d candidates · padding with uncertain",
            len(verdicts),
            len(candidates),
        )
        padded = list(verdicts)
        for missing in candidates[len(verdicts) :]:
            padded.append(
                TransliterationVerdict(
                    candidate=missing,
                    status="uncertain",
                    reason="validator response truncated",
                )
            )
        verdicts = tuple(padded)

    logger.info("validator returned %d verdict(s)", len(verdicts))
    return TransliterationReport(
        source_lang=source_lang,
        candidates_found=len(candidates),
        verdicts=verdicts,
        status="ok",
    )
