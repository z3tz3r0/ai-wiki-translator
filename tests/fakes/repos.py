"""In-memory FakePromptRepo and FakeGlossaryRepo for Phase 2 contract tests."""

from __future__ import annotations

from app.domain.values import Glossary


class FakePromptRepo:
    """Returns canned template strings; raises KeyError on unknown id.

    Structurally satisfies `app.application.ports.PromptTemplateRepository`.
    """

    def __init__(self, templates: dict[str, str] | None = None) -> None:
        self._templates: dict[str, str] = templates or {}

    async def load(self, template_id: str) -> str:
        return self._templates[template_id]


class FakeGlossaryRepo:
    """Returns a seeded `Glossary` regardless of `path`.

    Structurally satisfies `app.application.ports.GlossaryRepository`.
    """

    def __init__(self, glossary: Glossary | None = None) -> None:
        self._glossary: Glossary = glossary or {}

    async def load(self, path: str | None) -> Glossary:
        return dict(self._glossary)
