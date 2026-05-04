"""RefreshRulesUseCase · scrape th.wiki rule pages and write JSON cache.

Orchestrator behind ``wiki-refresh-rules`` CLI. Calls the
``TransliterationRuleSource`` port for each requested language and persists
the result via ``write_cache`` from ``app.infrastructure.transliteration_rules``.

The use case **swallows per-lang scrape errors** (``UnsupportedLanguage``,
``RulePageParseError``) so that ``--all`` doesn't bail on one bad page;
each lang gets a ``RefreshResult`` with ``ok=False`` and the message.
Other exceptions (``httpx`` errors, ``OSError``) propagate up · the CLI
layer catches them and exits non-zero.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from app.application.ports import TransliterationRuleSource
from app.infrastructure.transliteration_rules import (
    RulePageParseError,
    UnsupportedLanguage,
    write_cache,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RefreshResult:
    """Per-lang outcome from a refresh run · CLI-internal, not in dto.py."""

    lang: str
    ok: bool
    path: Path | None
    error: str | None


@dataclass(frozen=True)
class RefreshRulesUseCase:
    source: TransliterationRuleSource
    rules_dir: Path

    async def execute(self, langs: Sequence[str]) -> list[RefreshResult]:
        logger.info("refreshing rules for langs: %s", list(langs))
        results: list[RefreshResult] = []
        for lang in langs:
            try:
                ruleset = await self.source.fetch(lang)
                path = await write_cache(self.rules_dir, ruleset)
                size = path.stat().st_size
                logger.info(
                    "parsed %d rule entries for %s, wrote %s (%d bytes)",
                    len(ruleset.entries),
                    lang,
                    path,
                    size,
                )
                results.append(RefreshResult(lang=lang, ok=True, path=path, error=None))
            except (UnsupportedLanguage, RulePageParseError) as exc:
                logger.warning("refresh failed for %s: %s", lang, exc)
                results.append(RefreshResult(lang=lang, ok=False, path=None, error=str(exc)))
        return results
