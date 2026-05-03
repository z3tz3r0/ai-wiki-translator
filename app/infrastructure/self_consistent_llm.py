"""SelfConsistentLLMTranslator · sample N translations and vote by structural fidelity.

Wraps any ``LLMTranslator`` Protocol implementation with N-sample voting:
fire ``samples`` parallel requests per call, score each candidate against
the source by structural-fidelity heuristics, and return the best one.

Why: translation models are noisy on long-form output · a single sample can
omit a ``[[REF_n]]`` marker, truncate mid-sentence, or hallucinate an extra
template. Sampling 3-5 times and picking the candidate that best preserves
the source's reference markers + length distribution lifts chrF on long
articles by ~1-3 points typically, at linear quota cost.

Picker:
1. Reject empty / whitespace-only candidates outright.
2. Score each remaining candidate by ``(ref_diff, len_diff_from_median)``.
   - ``ref_diff`` = absolute difference between candidate's ``[[REF_n]]``
     count and the source's count. Primary signal · loses any candidate
     that dropped a reference marker.
   - ``len_diff_from_median`` = absolute difference from the median length
     across non-empty candidates. Tiebreak that punishes both truncation
     and runaway verbosity.
3. Lowest score wins. Stable on ties (Python's ``min`` returns the first).
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass

from app.application.ports import LLMTranslator

_REF_MARKER = re.compile(r"\[\[REF_\d+\]\]")


@dataclass(frozen=True)
class SelfConsistentLLMTranslator:
    """`LLMTranslator` wrapper that samples ``inner.translate_section`` ``samples`` times.

    With ``samples=1`` (the default), behavior is identical to the bare
    inner adapter · zero overhead, so this wrapper is safe to leave in
    place even when sampling is disabled.
    """

    inner: LLMTranslator
    samples: int = 1

    async def translate_section(self, content: str, system_instruction: str) -> str:
        if self.samples <= 1:
            return await self.inner.translate_section(content, system_instruction)

        candidates = await asyncio.gather(
            *(
                self.inner.translate_section(content, system_instruction)
                for _ in range(self.samples)
            )
        )
        return pick_best(content, list(candidates))


def pick_best(source: str, candidates: list[str]) -> str:
    """Return the candidate with the best structural fidelity to ``source``."""
    if not candidates:
        return ""
    non_empty = [c for c in candidates if c and c.strip()]
    if not non_empty:
        return candidates[0]

    expected_refs = len(_REF_MARKER.findall(source))
    lengths = sorted(len(c) for c in non_empty)
    median_len = lengths[len(lengths) // 2]

    def score(c: str) -> tuple[int, int]:
        actual_refs = len(_REF_MARKER.findall(c))
        return (abs(actual_refs - expected_refs), abs(len(c) - median_len))

    return min(non_empty, key=score)
