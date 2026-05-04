"""In-memory `TransliterationRuleSource` for use-case + CLI tests."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.application.dto import LanguageRuleSet
from app.infrastructure.transliteration_rules import UnsupportedLanguage


@dataclass
class FakeTransliterationRuleSource:
    """Maps lang → result or pre-staged exception.

    Mutable (not frozen) so tests can populate ``results``/``raises`` in
    setup. Mirrors the shape of other fakes under ``tests/fakes/``.
    """

    results: dict[str, LanguageRuleSet] = field(default_factory=dict)
    raises: dict[str, Exception] = field(default_factory=dict)

    async def fetch(self, lang: str) -> LanguageRuleSet:
        if lang in self.raises:
            raise self.raises[lang]
        if lang not in self.results:
            raise UnsupportedLanguage(f"fake has no result for {lang!r}")
        return self.results[lang]
