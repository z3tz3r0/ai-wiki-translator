"""LiteValidatorAdapter · multi-key google-genai client for transliteration judging.

``TransliterationValidator`` Protocol implementation. Sends one batched
call per article (regardless of candidate count) to Gemini Flash-Lite,
asks for JSON-formatted verdicts, parses them back into typed
``TransliterationVerdict`` tuples.

Mirrors ``GeminiAssistantAdapter``'s multi-key load balancing,
per-key throttle, and 429/503 retry logic. Differences:

* Generation config sets ``response_mime_type="application/json"`` so
  the model returns parseable JSON (Gemini honors this in Lite).
* On parse failure (malformed JSON, length mismatch, missing fields),
  falls back to ``uncertain`` for every candidate · the orchestrator
  treats this as ``ok`` status with degraded verdicts, not a
  ``skipped`` gate run.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from google.genai import types

from app.application.dto import (
    LanguageRuleSet,
    TransliterationCandidate,
    TransliterationVerdict,
)

logger = logging.getLogger(__name__)

_STATUS_VALUES: frozenset[str] = frozenset({"approved", "flagged", "uncertain"})


@dataclass
class LiteValidatorAdapter:
    """`TransliterationValidator` Protocol implementation backed by Gemini Flash-Lite.

    Construct with one or more ``genai.Client`` instances and the
    system-instruction template (loaded from
    ``app/prompts/transliteration_judge.md``).
    """

    clients: list[Any]
    judge_template: str
    model: str = "gemini-flash-lite-latest"
    requests_per_minute: int = 12
    max_retries: int = 1
    _last_call_at: list[float] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.clients:
            raise ValueError("`clients` must contain at least one Gemini client")
        if not self.judge_template.strip():
            raise ValueError("`judge_template` must be non-empty")
        self._last_call_at = [0.0] * len(self.clients)

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
        """Multi-key call with retry · returns the LLM's text response or None."""
        sleeps_left = self.max_retries
        failed_in_burst: set[int] = set()
        last_exc: Exception | None = None

        while True:
            key_index = self._pick_freshest_key(exclude=failed_in_burst)
            if key_index is None:
                if sleeps_left <= 0 or last_exc is None:
                    return None
                attempt = self.max_retries - sleeps_left
                delay = _retry_delay_seconds(last_exc, attempt=attempt)
                logger.warning(
                    "all %d keys exhausted on %s · sleeping %.1fs",
                    len(self.clients),
                    type(last_exc).__name__,
                    delay,
                )
                sleeps_left -= 1
                await asyncio.sleep(delay)
                failed_in_burst.clear()
                continue

            await self._throttle(key_index)
            try:
                config = types.GenerateContentConfig(
                    system_instruction=self.judge_template,
                    response_mime_type="application/json",
                )
                response = await self.clients[key_index].aio.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=config,
                )
                self._last_call_at[key_index] = time.monotonic()
                return response.text or ""
            except Exception as exc:
                last_exc = exc
                self._last_call_at[key_index] = time.monotonic()
                if not _is_retriable(exc):
                    raise
                logger.info(
                    "key=%d failed with %s · rotating",
                    key_index,
                    type(exc).__name__,
                )
                failed_in_burst.add(key_index)

    def _pick_freshest_key(self, exclude: set[int]) -> int | None:
        candidates = [i for i in range(len(self.clients)) if i not in exclude]
        if not candidates:
            return None
        return min(candidates, key=lambda i: self._last_call_at[i])

    async def _throttle(self, key_index: int) -> None:
        last_at = self._last_call_at[key_index]
        if last_at == 0.0:
            return
        gap = 60.0 / self.requests_per_minute
        elapsed = time.monotonic() - last_at
        if elapsed < gap:
            await asyncio.sleep(gap - elapsed)


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


def _is_retriable(exc: Exception) -> bool:
    return getattr(exc, "code", None) in (429, 503)


def _retry_delay_seconds(exc: Exception, attempt: int = 0) -> float:
    if getattr(exc, "code", None) == 503:
        return min(2.0**attempt, 30.0)
    details = getattr(exc, "details", None) or []
    if not isinstance(details, list):
        return 60.0
    for d in details:
        if not isinstance(d, dict):
            continue
        if not str(d.get("@type", "")).endswith("RetryInfo"):
            continue
        raw = d.get("retryDelay", "60s")
        if isinstance(raw, str) and raw.endswith("s"):
            try:
                return float(raw[:-1])
            except ValueError:
                pass
    return 60.0
