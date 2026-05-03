"""In-memory FakeWikidataReader for Phase 2 contract tests."""

from __future__ import annotations


class FakeWikidataReader:
    """Returns canned Q-IDs and claims dicts.

    Structurally satisfies `app.application.ports.WikidataReader`.
    """

    def __init__(
        self,
        qids: dict[tuple[str, str], str] | None = None,
        claims: dict[str, dict[str, list[str]]] | None = None,
    ) -> None:
        self._qids: dict[tuple[str, str], str] = qids or {}
        self._claims: dict[str, dict[str, list[str]]] = claims or {}

    async def resolve_qid(self, title: str, lang: str) -> str | None:
        return self._qids.get((title, lang))

    async def fetch_claims(self, qid: str) -> dict[str, list[str]]:
        return {k: list(v) for k, v in self._claims.get(qid, {}).items()}
