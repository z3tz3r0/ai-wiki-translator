"""LiteValidatorAdapter · multi-key google-genai client for transliteration judging.

``TransliterationValidator`` Protocol implementation. Sends one batched
call per article (regardless of candidate count) to Gemini Flash-Lite,
asks for JSON-formatted verdicts, parses them back into typed
``TransliterationVerdict`` tuples.

Key rotation and quota handling come from ``GeminiKeyPool``, which this
adapter can share with ``GeminiAssistantAdapter``. Differences:

* Generation config sets ``response_mime_type="application/json"`` so
  the model returns parseable JSON (Gemini honors this in Lite).
* When quota or model capacity runs out, every candidate comes back
  ``uncertain`` instead of raising. Other errors still raise.
* On parse failure (malformed JSON, length mismatch, missing fields),
  falls back to ``uncertain`` for every candidate · the orchestrator
  treats this as ``ok`` status with degraded verdicts, not a
  ``skipped`` gate run.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from google.genai import types

from app.application.dto import (
    LanguageRuleSet,
    TransliterationCandidate,
    TransliterationVerdict,
)
from app.infrastructure.gemini_key_pool import (
    DEFAULT_GEMINI_MODEL,
    GeminiKeyPool,
    is_quota_exhaustion,
)

logger = logging.getLogger(__name__)

_STATUS_VALUES: frozenset[str] = frozenset({"approved", "flagged", "uncertain"})


@dataclass
class LiteValidatorAdapter:
    """`TransliterationValidator` Protocol implementation backed by Gemini Flash-Lite.

    Construct with the system-instruction template (loaded from
    ``app/prompts/transliteration_judge.md``) plus the ``pool`` that holds
    the keys, throttle and retry settings, shared with the translator.
    """

    pool: GeminiKeyPool
    judge_template: str = ""
    model: str = DEFAULT_GEMINI_MODEL

    def __post_init__(self) -> None:
        if not self.judge_template.strip():
            raise ValueError("`judge_template` must be non-empty")

    async def validate(
        self,
        candidates: tuple[TransliterationCandidate, ...],
        rules: LanguageRuleSet,
    ) -> tuple[TransliterationVerdict, ...]:
        if not candidates:
            return ()
        prompt = _build_user_prompt(candidates, rules)
        raw = await self._generate_json(prompt)
        if raw is None:
            logger.warning(
                "validator call failed for lang=%s · returning %d uncertain verdicts",
                rules.lang,
                len(candidates),
            )
            return _all_uncertain(candidates, "validator call failed")
        verdicts = _parse_verdicts(raw, candidates)
        if verdicts is None:
            logger.warning(
                "validator JSON parse failed for lang=%s · returning %d uncertain verdicts",
                rules.lang,
                len(candidates),
            )
            return _all_uncertain(candidates, "validator response was not parseable JSON")
        return verdicts

    async def _generate_json(self, prompt: str) -> str | None:
        """One pooled call · the LLM's text, or None when quota or capacity ran out."""
        config = types.GenerateContentConfig(
            system_instruction=self.judge_template,
            response_mime_type="application/json",
        )

        async def request(client: Any) -> str:
            response = await client.aio.models.generate_content(
                model=self.model, contents=prompt, config=config
            )
            return response.text or ""

        try:
            return await self.pool.run(request)
        except Exception as exc:
            if is_quota_exhaustion(exc):
                return None
            raise


def _build_user_prompt(
    candidates: tuple[TransliterationCandidate, ...],
    rules: LanguageRuleSet,
) -> str:
    """Render rule excerpt + candidates as a single user-message payload."""
    payload = {
        "source_lang": rules.lang,
        "rule_excerpt": rules.excerpt,
        "candidates": [
            {
                "index": i,
                "thai": c.thai,
                "latin_hint": c.latin_hint,
                "context": c.context,
            }
            for i, c in enumerate(candidates)
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _parse_verdicts(
    raw: str,
    candidates: tuple[TransliterationCandidate, ...],
) -> tuple[TransliterationVerdict, ...] | None:
    """Decode JSON list of verdict objects into typed tuple, or None on failure.

    Returns ``None`` (not all-uncertain) so the caller can distinguish
    "validator gave bad output" from a successful all-uncertain
    response. The caller wraps None into a uniform fallback.
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("validator JSON decode failed: %s", exc)
        return None
    if not isinstance(data, list):
        logger.warning("validator JSON was not a list: %s", type(data).__name__)
        return None
    if len(data) != len(candidates):
        logger.warning(
            "validator returned %d items for %d candidates",
            len(data),
            len(candidates),
        )
        return None

    out: list[TransliterationVerdict] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            return None
        status = str(item.get("status", "uncertain"))
        if status not in _STATUS_VALUES:
            status = "uncertain"
        out.append(
            TransliterationVerdict(
                candidate=candidates[i],
                status=status,  # type: ignore[arg-type]
                rule_citation=str(item.get("rule_citation", "")),
                suggested=str(item.get("suggested", "")),
                reason=str(item.get("reason", "")),
            )
        )
    return tuple(out)


def _all_uncertain(
    candidates: tuple[TransliterationCandidate, ...],
    reason: str,
) -> tuple[TransliterationVerdict, ...]:
    return tuple(
        TransliterationVerdict(candidate=c, status="uncertain", reason=reason) for c in candidates
    )
