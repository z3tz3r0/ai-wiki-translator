"""WikidataHttpReader · resolve QIDs + fetch claims via Wikidata + Wikipedia.

Two endpoints:

* ``https://<lang>.wikipedia.org/w/api.php?action=query&prop=pageprops`` to
  read the ``wikibase_item`` (Q-ID) attached to a wiki page.
* ``https://www.wikidata.org/wiki/Special:EntityData/<qid>.json`` for the
  entity's claims.

Claim values are returned as Q-ID strings for ``wikibase-entityid``
mainsnaks. Other claim datatypes (string, time, quantity) are skipped
in Phase 4 · the source picker only consumes entity references today.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

DEFAULT_USER_AGENT = "ai-wiki-translator/0.1 (https://github.com/z3tz3r0/ai-wiki-translator)"


@dataclass(frozen=True)
class WikidataHttpReader:
    """`WikidataReader` Protocol implementation backed by live Wikidata."""

    transport: httpx.AsyncBaseTransport | None = None
    user_agent: str = DEFAULT_USER_AGENT
    timeout: float = 30.0

    async def resolve_qid(self, title: str, lang: str) -> str | None:
        async with self._client(f"https://{lang}.wikipedia.org") as client:
            response = await client.get(
                "/w/api.php",
                params={
                    "action": "query",
                    "titles": title,
                    "prop": "pageprops",
                    "format": "json",
                    "formatversion": "2",
                    "redirects": "1",
                },
            )
            response.raise_for_status()
            payload: dict[str, Any] = response.json()
        pages = payload.get("query", {}).get("pages", [])
        if not isinstance(pages, list) or not pages:
            return None
        first = pages[0]
        if not isinstance(first, dict) or first.get("missing"):
            return None
        pageprops = first.get("pageprops", {})
        if not isinstance(pageprops, dict):
            return None
        wikibase_item = pageprops.get("wikibase_item")
        return wikibase_item if isinstance(wikibase_item, str) else None

    async def fetch_claims(self, qid: str) -> dict[str, list[str]]:
        async with self._client("https://www.wikidata.org") as client:
            response = await client.get(f"/wiki/Special:EntityData/{qid}.json")
            response.raise_for_status()
            payload: dict[str, Any] = response.json()
        entities = payload.get("entities", {})
        if not isinstance(entities, dict):
            return {}
        entity = entities.get(qid, {})
        if not isinstance(entity, dict):
            return {}
        raw_claims = entity.get("claims", {})
        if not isinstance(raw_claims, dict):
            return {}
        return _extract_entity_claims(raw_claims)

    def _client(self, base_url: str) -> httpx.AsyncClient:
        kwargs: dict[str, Any] = {
            "base_url": base_url,
            "headers": {"User-Agent": self.user_agent},
            "timeout": self.timeout,
        }
        if self.transport is not None:
            kwargs["transport"] = self.transport
        return httpx.AsyncClient(**kwargs)


def _extract_entity_claims(raw_claims: dict[str, Any]) -> dict[str, list[str]]:
    """Flatten Wikidata claims into ``{Pxx: [Qxx, ...]}`` for entity references."""
    result: dict[str, list[str]] = {}
    for prop_id, statements in raw_claims.items():
        if not isinstance(prop_id, str) or not isinstance(statements, list):
            continue
        values: list[str] = []
        for stmt in statements:
            qid = _entity_value_from_statement(stmt)
            if qid is not None:
                values.append(qid)
        if values:
            result[prop_id] = values
    return result


def _entity_value_from_statement(stmt: Any) -> str | None:
    if not isinstance(stmt, dict):
        return None
    mainsnak = stmt.get("mainsnak")
    if not isinstance(mainsnak, dict):
        return None
    if mainsnak.get("snaktype") != "value":
        return None
    datavalue = mainsnak.get("datavalue")
    if not isinstance(datavalue, dict):
        return None
    if datavalue.get("type") != "wikibase-entityid":
        return None
    value = datavalue.get("value")
    if not isinstance(value, dict):
        return None
    qid = value.get("id")
    return qid if isinstance(qid, str) else None
