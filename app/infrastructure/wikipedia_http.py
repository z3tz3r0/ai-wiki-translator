"""WikipediaHttpReader · MediaWiki API client via httpx.

Hits ``https://<lang>.wikipedia.org/w/api.php`` with ``action=parse``.
Tests inject an ``httpx.MockTransport`` to short-circuit the network.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import httpx

from app.domain.entities import Article
from app.domain.references import remove_comments, strip_references
from app.domain.values import ArticleTitle

_WIKILINK_RE = re.compile(r"\[\[(?!File:|Category:)([^#|\]]+)(?:#[^|\]]*)?(?:\|[^\]]+)?\]\]")

DEFAULT_USER_AGENT = "ai-wiki-translator/0.1 (https://github.com/z3tz3r0/ai-wiki-translator)"


@dataclass(frozen=True)
class WikipediaHttpReader:
    """`WikipediaReader` Protocol implementation backed by the live MediaWiki API."""

    transport: httpx.AsyncBaseTransport | None = None
    user_agent: str = DEFAULT_USER_AGENT
    timeout: float = 30.0

    async def fetch_article(self, title: str, lang: str) -> Article | None:
        data = await self._get_parse(title, lang, prop="wikitext")
        if data is None:
            return None
        wikitext = data.get("wikitext", "")
        if not isinstance(wikitext, str):
            return None
        stripped = remove_comments(wikitext)
        wikitext_no_ref, ref_map = strip_references(stripped)
        wikilinks = _extract_wikilinks(wikitext_no_ref)
        return Article(
            title=ArticleTitle(title),
            wikitext=wikitext,
            wikitext_no_ref=wikitext_no_ref,
            ref_map=ref_map,
            wikilinks=wikilinks,
            dictionary={},
        )

    async def fetch_langlinks(self, title: str, lang: str) -> dict[str, str]:
        data = await self._get_parse(title, lang, prop="langlinks")
        if data is None:
            return {}
        raw_links = data.get("langlinks", [])
        if not isinstance(raw_links, list):
            return {}
        result: dict[str, str] = {}
        for entry in raw_links:
            if not isinstance(entry, dict):
                continue
            ll_lang = entry.get("lang")
            ll_title = entry.get("title")
            if isinstance(ll_lang, str) and isinstance(ll_title, str):
                result[ll_lang] = ll_title
        return result

    async def _get_parse(self, title: str, lang: str, *, prop: str) -> dict[str, Any] | None:
        """Run ``action=parse&page=<title>&prop=<prop>``; return the ``parse`` dict.

        Returns ``None`` when MediaWiki responds with a top-level ``error``
        (typically ``missingtitle``).
        """
        async with self._client(lang) as client:
            response = await client.get(
                "/w/api.php",
                params={
                    "action": "parse",
                    "page": title,
                    "prop": prop,
                    "format": "json",
                    "formatversion": "2",
                    "redirects": "1",
                },
            )
            response.raise_for_status()
            payload: dict[str, Any] = response.json()
        if "error" in payload:
            return None
        parse = payload.get("parse")
        if not isinstance(parse, dict):
            return None
        return parse

    def _client(self, lang: str) -> httpx.AsyncClient:
        kwargs: dict[str, Any] = {
            "base_url": f"https://{lang}.wikipedia.org",
            "headers": {"User-Agent": self.user_agent},
            "timeout": self.timeout,
        }
        if self.transport is not None:
            kwargs["transport"] = self.transport
        return httpx.AsyncClient(**kwargs)


def _extract_wikilinks(wikitext: str) -> list[str]:
    """Return wikilink targets in source order, deduplicated.

    Skips ``File:`` and ``Category:`` prefixes. Display text after ``|`` is
    discarded; section anchors after ``#`` are discarded.
    """
    seen: set[str] = set()
    out: list[str] = []
    for match in _WIKILINK_RE.finditer(wikitext):
        target = match.group(1).strip()
        if not target or target in seen:
            continue
        seen.add(target)
        out.append(target)
    return out
