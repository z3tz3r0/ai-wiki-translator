"""In-memory FakeWikipediaReader for Phase 2 contract tests."""

from __future__ import annotations

from app.domain.entities import Article


class FakeWikipediaReader:
    """Returns canned `Article` instances and langlinks dicts.

    Structurally satisfies `app.application.ports.WikipediaReader`
    without inheritance · Protocols are duck-typed.
    """

    def __init__(
        self,
        articles: dict[tuple[str, str], Article] | None = None,
        langlinks: dict[tuple[str, str], dict[str, str]] | None = None,
    ) -> None:
        self._articles: dict[tuple[str, str], Article] = articles or {}
        self._langlinks: dict[tuple[str, str], dict[str, str]] = langlinks or {}

    async def fetch_article(self, title: str, lang: str) -> Article | None:
        return self._articles.get((title, lang))

    async def fetch_langlinks(self, title: str, lang: str) -> dict[str, str]:
        return dict(self._langlinks.get((title, lang), {}))
