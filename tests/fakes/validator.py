"""In-memory `TransliterationValidator` for service + use-case tests."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from app.application.dto import (
    LanguageRuleSet,
    TransliterationCandidate,
    TransliterationVerdict,
)


@dataclass
class FakeTransliterationValidator:
    """Configurable fake.

    ``verdicts_by_thai`` lets tests pre-stage a verdict per ``thai``
    string. Candidates without an entry get a default ``approved``
    verdict (or one produced by ``default_factory`` when set).
    ``raises`` triggers an exception on the call when set · used to
    verify the orchestrator's error propagation.

    Mutable (not frozen) so tests can populate fields in setup.
    """

    verdicts_by_thai: dict[str, TransliterationVerdict] = field(default_factory=dict)
    default_factory: Callable[[TransliterationCandidate], TransliterationVerdict] | None = None
    raises: Exception | None = None
    calls: list[tuple[tuple[TransliterationCandidate, ...], LanguageRuleSet]] = field(
        default_factory=list
    )

    async def validate(
        self,
        candidates: tuple[TransliterationCandidate, ...],
        rules: LanguageRuleSet,
    ) -> tuple[TransliterationVerdict, ...]:
        if self.raises is not None:
            raise self.raises
        self.calls.append((candidates, rules))
        out: list[TransliterationVerdict] = []
        for c in candidates:
            if c.thai in self.verdicts_by_thai:
                out.append(self.verdicts_by_thai[c.thai])
            elif self.default_factory is not None:
                out.append(self.default_factory(c))
            else:
                out.append(
                    TransliterationVerdict(
                        candidate=c,
                        status="approved",
                        reason="fake default",
                    )
                )
        return tuple(out)
