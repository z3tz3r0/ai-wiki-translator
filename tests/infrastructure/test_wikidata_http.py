"""Tests for `WikidataHttpReader` · QID resolution + claims fetch."""

from __future__ import annotations

import os
from typing import Any

import httpx
import pytest

from app.application.ports import WikidataReader
from app.infrastructure.wikidata_http import WikidataHttpReader


def _route(handler_map: dict[str, Any]) -> httpx.MockTransport:
    """Dispatch on substring match in the request URL string."""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        for prefix, body in handler_map.items():
            if prefix in url:
                if isinstance(body, int):
                    return httpx.Response(body)
                return httpx.Response(200, json=body)
        return httpx.Response(404, json={"error": "no route"})

    return httpx.MockTransport(handler)


def test_satisfies_wikidata_reader_protocol() -> None:
    reader = WikidataHttpReader(transport=_route({}))
    assert isinstance(reader, WikidataReader)


# --- resolve_qid ------------------------------------------------------------


async def test_resolve_qid_returns_wikibase_item() -> None:
    transport = _route(
        {
            "en.wikipedia.org/w/api.php": {
                "query": {
                    "pages": [
                        {
                            "title": "Narcissism",
                            "pageprops": {"wikibase_item": "Q179681"},
                        }
                    ]
                }
            }
        }
    )
    reader = WikidataHttpReader(transport=transport)
    assert await reader.resolve_qid("Narcissism", "en") == "Q179681"


async def test_resolve_qid_missing_page_returns_none() -> None:
    transport = _route(
        {"en.wikipedia.org/w/api.php": {"query": {"pages": [{"missing": True, "title": "Nope"}]}}}
    )
    reader = WikidataHttpReader(transport=transport)
    assert await reader.resolve_qid("Nope", "en") is None


async def test_resolve_qid_no_pageprops_returns_none() -> None:
    transport = _route({"en.wikipedia.org/w/api.php": {"query": {"pages": [{"title": "Plain"}]}}})
    reader = WikidataHttpReader(transport=transport)
    assert await reader.resolve_qid("Plain", "en") is None


async def test_resolve_qid_empty_pages_returns_none() -> None:
    transport = _route({"en.wikipedia.org/w/api.php": {"query": {"pages": []}}})
    reader = WikidataHttpReader(transport=transport)
    assert await reader.resolve_qid("X", "en") is None


# --- fetch_claims -----------------------------------------------------------


def _entity(qid: str, claims: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    return {"entities": {qid: {"id": qid, "claims": claims}}}


def _entity_claim(prop: str, value_qid: str) -> dict[str, Any]:
    return {
        "mainsnak": {
            "snaktype": "value",
            "property": prop,
            "datavalue": {
                "type": "wikibase-entityid",
                "value": {"entity-type": "item", "id": value_qid},
            },
        }
    }


async def test_fetch_claims_extracts_wikibase_entityid_qids() -> None:
    transport = _route(
        {
            "Special:EntityData/Q179681.json": _entity(
                "Q179681",
                {"P17": [_entity_claim("P17", "Q30")]},
            )
        }
    )
    reader = WikidataHttpReader(transport=transport)
    claims = await reader.fetch_claims("Q179681")
    assert claims == {"P17": ["Q30"]}


async def test_fetch_claims_handles_multiple_values_per_property() -> None:
    transport = _route(
        {
            "Special:EntityData/Q42.json": _entity(
                "Q42",
                {
                    "P17": [
                        _entity_claim("P17", "Q30"),
                        _entity_claim("P17", "Q145"),
                    ]
                },
            )
        }
    )
    reader = WikidataHttpReader(transport=transport)
    claims = await reader.fetch_claims("Q42")
    assert claims == {"P17": ["Q30", "Q145"]}


async def test_fetch_claims_skips_non_entity_value_types() -> None:
    """String / time / quantity claims are skipped (only entityid mapped today)."""
    transport = _route(
        {
            "Special:EntityData/Q42.json": _entity(
                "Q42",
                {
                    "P17": [_entity_claim("P17", "Q30")],
                    "P31": [
                        {
                            "mainsnak": {
                                "snaktype": "value",
                                "property": "P31",
                                "datavalue": {
                                    "type": "string",
                                    "value": "some-string-value",
                                },
                            }
                        }
                    ],
                },
            )
        }
    )
    reader = WikidataHttpReader(transport=transport)
    claims = await reader.fetch_claims("Q42")
    assert claims == {"P17": ["Q30"]}


async def test_fetch_claims_skips_novalue_snaks() -> None:
    transport = _route(
        {
            "Special:EntityData/Q42.json": _entity(
                "Q42",
                {
                    "P17": [
                        {"mainsnak": {"snaktype": "novalue", "property": "P17"}},
                        _entity_claim("P17", "Q30"),
                    ]
                },
            )
        }
    )
    reader = WikidataHttpReader(transport=transport)
    claims = await reader.fetch_claims("Q42")
    assert claims == {"P17": ["Q30"]}


async def test_fetch_claims_no_entity_returns_empty_dict() -> None:
    transport = _route({"Special:EntityData/Q999.json": {"entities": {}}})
    reader = WikidataHttpReader(transport=transport)
    assert await reader.fetch_claims("Q999") == {}


# --- integration ------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("CI") is not None,
    reason="integration tests hit live Wikidata · run locally with `pytest -m integration`",
)
async def test_integration_resolve_qid_against_live_wikipedia() -> None:
    reader = WikidataHttpReader()
    qid = await reader.resolve_qid("Narcissism", "en")
    assert qid is not None
    assert qid.startswith("Q")
