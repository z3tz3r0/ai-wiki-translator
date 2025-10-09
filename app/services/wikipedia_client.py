"""Utilities for retrieving and preparing Wikipedia content."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Set, Tuple

import requests


@dataclass
class WikipediaPage:
    """Container for processed Wikipedia content."""

    title: str
    wikitext: str
    wikitext_no_ref: str
    ref_map: Dict[str, str]
    wikilinks: List[str]
    dictionary: Dict[str, str]
    missing_translations: Set[str]

    def replace_references(self, text: str) -> str:
        """Replace numeric placeholders with their reference tags."""

        def replacement(match: re.Match[str]) -> str:
            ref_number = match.group(0)
            return self.ref_map.get(ref_number, ref_number)

        pattern = r"\[(\d+)\]"
        return re.sub(pattern, replacement, text)

    @staticmethod
    def convert_to_list(text: str) -> List[str]:
        """Split wikitext into significant blocks for downstream processing."""
        pattern = r"^.*\n*(?:\s?\|.*|\*\s*\[*.*\n?|\s?\}.*|\{\|.*|!.*|\(.*)*\s*\n*"
        matches = re.findall(pattern, text, flags=re.MULTILINE)
        return [match.strip() for match in matches if match.strip()]


class WikipediaClient:
    """Fetches and prepares Wikipedia articles using the MediaWiki API."""

    API_URL = "https://en.wikipedia.org/w/api.php"

    def fetch_page(self, title: str) -> WikipediaPage:
        page = self._fetch_raw_page(title)
        wikitext = self._extract_wikitext(page)
        wikilinks = self._extract_internal_links(page)
        wikitext_no_ref, ref_map = self._strip_reference_tags(wikitext)
        dictionary, missing = self._map_th_titles(wikilinks, source_lang="en", target_lang="th")

        return WikipediaPage(
            title=title,
            wikitext=wikitext,
            wikitext_no_ref=wikitext_no_ref,
            ref_map=ref_map,
            wikilinks=wikilinks,
            dictionary=dictionary,
            missing_translations=missing,
        )

    def _fetch_raw_page(self, title: str) -> Dict:
        params = {
            "action": "parse",
            "format": "json",
            "page": title,
            "prop": "links|wikitext",
            "formatversion": "2",
        }
        response = requests.get(self.API_URL, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        return data["parse"]

    @staticmethod
    def _extract_wikitext(page: Dict) -> str:
        return page["wikitext"]

    @staticmethod
    def _extract_internal_links(page: Dict) -> List[str]:
        return [link["title"] for link in page.get("links", [])]

    @staticmethod
    def _strip_reference_tags(wikitext: str) -> Tuple[str, Dict[str, str]]:
        ref_map: Dict[str, str] = {}
        ref_count = 1

        def replacement(match: re.Match[str]) -> str:
            nonlocal ref_count
            ref_number = f"[{ref_count}]"
            ref_map[ref_number] = match.group(0)
            ref_count += 1
            return ref_number

        pattern = r"<ref(?:[^>]*)?>(?:[^<]*<\/ref>)?"
        result = re.sub(pattern, replacement, wikitext)
        return result, ref_map

    def _map_th_titles(
        self, titles: Iterable[str], source_lang: str, target_lang: str
    ) -> Tuple[Dict[str, str], Set[str]]:
        url = f"https://{source_lang}.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "titles": "",
            "prop": "langlinks",
            "lllang": target_lang,
            "redirects": 1,
            "format": "json",
        }

        title_mapping: Dict[str, str] = {}
        missing: Set[str] = set()

        def process_response(data: Dict) -> None:
            pages = data.get("query", {}).get("pages", {})
            for page_data in pages.values():
                title = page_data.get("title")
                if not title:
                    continue
                langlinks = page_data.get("langlinks") or []
                if langlinks:
                    translated = langlinks[0].get("*")
                    if translated:
                        title_mapping[title] = translated
                        continue
                missing.add(title)

        last_continue: Dict[str, str] = {}
        titles_list = list(titles)
        for start in range(0, len(titles_list), 50):
            batch = titles_list[start : start + 50]
            last_continue = {}
            while True:
                request_params = {**params, **last_continue, "titles": "|".join(batch)}
                response = requests.get(url, params=request_params, timeout=30)
                response.raise_for_status()
                try:
                    result = response.json()
                except json.JSONDecodeError as exc:  # pragma: no cover - defensive
                    raise ValueError("Malformed response from Wikipedia API") from exc
                if "error" in result:
                    raise ValueError(str(result["error"]))
                process_response(result)
                if "continue" not in result:
                    break
                last_continue = result.get("continue", {})

        return title_mapping, missing

