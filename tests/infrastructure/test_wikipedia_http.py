"""Tests for `WikipediaHttpReader` · MediaWiki API via httpx + MockTransport."""

from __future__ import annotations

import os
from typing import Any

import httpx
import pytest

from app.application.ports import WikipediaReader
from app.domain.values import ArticleTitle
from app.infrastructure.wikipedia_http import WikipediaHttpReader


def _make_transport(
    routes: dict[tuple[str, str], dict[str, Any]],
) -> httpx.MockTransport:
    """Map ``(host, page)`` -> response JSON.

    Falls through to ``{"error": {"code": "missingtitle"}}`` for unknown pages.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path != "/w/api.php":
            return httpx.Response(404, json={"error": {"code": "unknown-endpoint"}})
        page = request.url.params.get("page", "")
        host = request.url.host
        body = routes.get((host, page))
        if body is None:
            return httpx.Response(200, json={"error": {"code": "missingtitle"}})
        return httpx.Response(200, json=body)

    return httpx.MockTransport(handler)


def test_satisfies_wikipedia_reader_protocol() -> None:
    transport = _make_transport({})
    reader = WikipediaHttpReader(transport=transport)
    assert isinstance(reader, WikipediaReader)


async def test_fetch_article_returns_article_for_existing_page() -> None:
    transport = _make_transport(
        {
            ("en.wikipedia.org", "Narcissism"): {
                "parse": {
                    "title": "Narcissism",
                    "pageid": 21492,
                    "wikitext": "Body of [[Ego]] article.",
                }
            }
        }
    )
    reader = WikipediaHttpReader(transport=transport)
    article = await reader.fetch_article("Narcissism", "en")
    assert article is not None
    assert article.title == ArticleTitle("Narcissism")
    assert article.wikitext == "Body of [[Ego]] article."


async def test_fetch_article_returns_none_for_missing_page() -> None:
    transport = _make_transport({})
    reader = WikipediaHttpReader(transport=transport)
    assert await reader.fetch_article("DoesNotExist", "en") is None


async def test_fetch_article_extracts_wikilinks() -> None:
    transport = _make_transport(
        {
            ("en.wikipedia.org", "Foo"): {
                "parse": {
                    "title": "Foo",
                    "wikitext": "Mentions [[Alpha]] and [[Beta|Beta link]].",
                }
            }
        }
    )
    reader = WikipediaHttpReader(transport=transport)
    article = await reader.fetch_article("Foo", "en")
    assert article is not None
    assert "Alpha" in article.wikilinks
    assert "Beta" in article.wikilinks


async def test_fetch_article_strips_references_and_populates_ref_map() -> None:
    transport = _make_transport(
        {
            ("en.wikipedia.org", "Foo"): {
                "parse": {
                    "title": "Foo",
                    "wikitext": "claim<ref>source A</ref> and another<ref>source B</ref>.",
                }
            }
        }
    )
    reader = WikipediaHttpReader(transport=transport)
    article = await reader.fetch_article("Foo", "en")
    assert article is not None
    assert "<ref>" not in article.wikitext_no_ref
    assert "[1]" in article.wikitext_no_ref
    assert article.ref_map["[1]"] == "<ref>source A</ref>"
    assert article.ref_map["[2]"] == "<ref>source B</ref>"


async def test_fetch_article_uses_correct_lang_subdomain() -> None:
    """Lang prefix routes to the right Wikipedia."""
    transport = _make_transport(
        {
            ("ja.wikipedia.org", "ナルシシズム"): {
                "parse": {
                    "title": "ナルシシズム",
                    "wikitext": "日本語の本文",
                }
            }
        }
    )
    reader = WikipediaHttpReader(transport=transport)
    article = await reader.fetch_article("ナルシシズム", "ja")
    assert article is not None
    assert article.wikitext == "日本語の本文"


async def test_fetch_article_sends_user_agent_header() -> None:
    seen_headers: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers.append(request.headers.get("user-agent", ""))
        return httpx.Response(200, json={"parse": {"title": "X", "wikitext": "body"}})

    reader = WikipediaHttpReader(
        transport=httpx.MockTransport(handler),
        user_agent="ai-wiki-translator-test/1.0 ([email protected])",
    )
    await reader.fetch_article("X", "en")
    assert seen_headers and "ai-wiki-translator-test" in seen_headers[0]


async def test_fetch_article_returns_empty_dictionary_for_use_case_to_fill() -> None:
    transport = _make_transport(
        {("en.wikipedia.org", "Foo"): {"parse": {"title": "Foo", "wikitext": "[[Alpha]]"}}}
    )
    reader = WikipediaHttpReader(transport=transport)
    article = await reader.fetch_article("Foo", "en")
    assert article is not None
    assert article.dictionary == {}


async def test_fetch_langlinks_returns_lang_to_title_dict() -> None:
    transport = _make_transport(
        {
            ("en.wikipedia.org", "Narcissism"): {
                "parse": {
                    "title": "Narcissism",
                    "langlinks": [
                        {"lang": "th", "title": "ความหลงตนเอง"},
                        {"lang": "ja", "title": "ナルシシズム"},
                    ],
                }
            }
        }
    )
    reader = WikipediaHttpReader(transport=transport)
    out = await reader.fetch_langlinks("Narcissism", "en")
    assert out == {"th": "ความหลงตนเอง", "ja": "ナルシシズム"}


async def test_fetch_langlinks_missing_page_returns_empty_dict() -> None:
    transport = _make_transport({})
    reader = WikipediaHttpReader(transport=transport)
    assert await reader.fetch_langlinks("DoesNotExist", "en") == {}


async def test_fetch_langlinks_no_langlinks_key_returns_empty_dict() -> None:
    transport = _make_transport(
        {
            ("en.wikipedia.org", "Foo"): {
                "parse": {"title": "Foo"}  # no langlinks field
            }
        }
    )
    reader = WikipediaHttpReader(transport=transport)
    assert await reader.fetch_langlinks("Foo", "en") == {}


async def test_fetch_article_raises_on_5xx_so_caller_can_retry() -> None:
    """Server errors must propagate; a 503 is not a `None` page."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="Service Unavailable")

    reader = WikipediaHttpReader(transport=httpx.MockTransport(handler))
    with pytest.raises(httpx.HTTPStatusError):
        await reader.fetch_article("Foo", "en")


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("CI") is not None,
    reason="integration tests hit live Wikipedia · run locally with `pytest -m integration`",
)
async def test_integration_fetch_article_against_live_wikipedia() -> None:
    reader = WikipediaHttpReader()
    article = await reader.fetch_article("Narcissism", "en")
    assert article is not None
    assert "Narcissism" in str(article.title)
    assert article.wikitext  # non-empty
