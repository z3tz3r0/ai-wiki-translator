"""WikipediaTransliterationRuleSource · th.wiki rule-page scraper via httpx + BS4.

Hits ``https://th.wikipedia.org/w/api.php`` with ``action=parse&prop=text``
to get pre-rendered HTML for a rule page (templates expanded by the server),
then parses the wikitables to extract grapheme→Thai entries. The free
functions ``read_cache`` and ``write_cache`` handle on-disk persistence as
``~/.cache/wiki-translator/rules/<lang>.json``.

The adapter is fetch-only · persistence lives in the module-level cache
helpers so the Protocol stays single-purpose. The CLI command
``wiki-refresh-rules`` (Phase 1, Task 6) wires fetch + write together via
``RefreshRulesUseCase``.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from bs4 import BeautifulSoup, Tag

from app.application.dto import LanguageRuleSet, RuleEntry

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = "ai-wiki-translator/0.1 (https://github.com/z3tz3r0/ai-wiki-translator)"
RULE_HOST = "https://th.wikipedia.org"

# Static map populated from a 2026-05-04 fetch of
# https://th.wikipedia.org/wiki/หลักเกณฑ์การทับศัพท์ของราชบัณฑิตยสถานและสำนักงานราชบัณฑิตยสภา
# (verified by enumerating the parent page's wikitext links · 15 style-guide
# child pages, no Royal-Society-direct pages on this index).
# Update by re-running the WebFetch / API probe described in Phase 1 Task 1.
LANG_TO_TITLE: dict[str, str] = {
    "en": "วิกิพีเดีย:คู่มือการเขียน/การทับศัพท์ภาษาอังกฤษ",
    "de": "วิกิพีเดีย:คู่มือการเขียน/การทับศัพท์ภาษาเยอรมัน",
    "it": "วิกิพีเดีย:คู่มือการเขียน/การทับศัพท์ภาษาอิตาลี",
    "fr": "วิกิพีเดีย:คู่มือการเขียน/การทับศัพท์ภาษาฝรั่งเศส",
    "es": "วิกิพีเดีย:คู่มือการเขียน/การทับศัพท์ภาษาสเปน",
    "ar": "วิกิพีเดีย:คู่มือการเขียน/การทับศัพท์ภาษาอาหรับ",
    "ru": "วิกิพีเดีย:คู่มือการเขียน/การทับศัพท์ภาษารัสเซีย",
    "ja": "วิกิพีเดีย:คู่มือการเขียน/การทับศัพท์ภาษาญี่ปุ่น",
    "ko": "วิกิพีเดีย:คู่มือการเขียน/การทับศัพท์ภาษาเกาหลี",
    "zh": "วิกิพีเดีย:คู่มือการเขียน/การทับศัพท์ภาษาจีน",
    "vi": "วิกิพีเดีย:คู่มือการเขียน/การทับศัพท์ภาษาเวียดนาม",
    "ms": "วิกิพีเดีย:คู่มือการเขียน/การทับศัพท์ภาษามลายู",
    "id": "วิกิพีเดีย:คู่มือการเขียน/การทับศัพท์ภาษาอินโดนีเซีย",
    "hi": "วิกิพีเดีย:คู่มือการเขียน/การทับศัพท์ภาษาฮินดี",
    "my": "วิกิพีเดีย:คู่มือการเขียน/การทับศัพท์ภาษาพม่า",
}


class UnsupportedLanguage(ValueError):
    """Raised when ``fetch(lang)`` is called with a lang not in ``LANG_TO_TITLE``."""


class RulePageParseError(RuntimeError):
    """Raised when the rule page HTML can't be parsed into ≥1 ``RuleEntry``."""


@dataclass(frozen=True)
class WikipediaTransliterationRuleSource:
    """`TransliterationRuleSource` Protocol implementation backed by live th.wiki."""

    transport: httpx.AsyncBaseTransport | None = None
    user_agent: str = DEFAULT_USER_AGENT
    timeout: float = 30.0

    async def fetch(self, lang: str) -> LanguageRuleSet:
        if lang not in LANG_TO_TITLE:
            raise UnsupportedLanguage(
                f"no th.wiki rule page registered for lang={lang!r} · "
                f"supported: {sorted(LANG_TO_TITLE)}"
            )
        title = LANG_TO_TITLE[lang]
        logger.info("fetching th.wiki rule page for %s (title=%r)", lang, title)
        html = await self._fetch_parse_text(title)
        if html is None:
            raise RulePageParseError(f"th.wiki returned no parse.text for {title!r} (lang={lang})")
        entries, excerpt = _parse_rule_html(html)
        if not entries:
            raise RulePageParseError(
                f"parsed 0 rule entries for lang={lang} title={title!r} · "
                "page layout may have changed"
            )
        logger.info("parsed %d rule entries for %s (title=%r)", len(entries), lang, title)
        return LanguageRuleSet(
            lang=lang,
            title=title,
            url=f"{RULE_HOST}/wiki/{title}",
            scraped_at=datetime.datetime.now(datetime.UTC).replace(tzinfo=None),
            entries=tuple(entries),
            excerpt=excerpt,
        )

    async def _fetch_parse_text(self, title: str) -> str | None:
        async with self._client() as client:
            response = await client.get(
                "/w/api.php",
                params={
                    "action": "parse",
                    "page": title,
                    "prop": "text",
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
        text = parse.get("text")
        return text if isinstance(text, str) else None

    def _client(self) -> httpx.AsyncClient:
        kwargs: dict[str, Any] = {
            "base_url": RULE_HOST,
            "headers": {"User-Agent": self.user_agent},
            "timeout": self.timeout,
        }
        if self.transport is not None:
            kwargs["transport"] = self.transport
        return httpx.AsyncClient(**kwargs)


def _parse_rule_html(html: str) -> tuple[list[RuleEntry], str]:
    """Extract ``RuleEntry`` rows from one or more wikitables.

    Selector strategy (most-tolerant first):

      1. find every ``table.wikitable``
      2. for each table: skip the header row, expect at least 2 cells per
         row (grapheme, thai), optional 3rd cell as notes
      3. concatenate all rows into the entry list; preserve source order

    The excerpt is the markdown form of the first 3 tables (joined with
    blank lines), suitable for pasting into an LLM-judge prompt later.
    """
    soup = BeautifulSoup(html, "lxml")
    tables = soup.find_all("table", class_="wikitable")
    entries: list[RuleEntry] = []
    excerpt_parts: list[str] = []
    for table in tables:
        if not isinstance(table, Tag):
            continue
        rows = table.find_all("tr")
        for row in rows[1:]:  # skip header
            if not isinstance(row, Tag):
                continue
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue
            grapheme = cells[0].get_text(strip=True)
            thai = cells[1].get_text(strip=True)
            if not grapheme or not thai:
                continue
            notes = cells[2].get_text(strip=True) if len(cells) >= 3 else ""
            entries.append(RuleEntry(grapheme=grapheme, thai=thai, notes=notes))
        if len(excerpt_parts) < 3:
            excerpt_parts.append(_table_to_markdown(table))
    excerpt = "\n\n".join(excerpt_parts)
    return entries, excerpt


def _table_to_markdown(table: Tag) -> str:
    """Render one BS4 ``<table>`` as a markdown table for LLM prompts."""
    lines: list[str] = []
    for row in table.find_all("tr"):
        if not isinstance(row, Tag):
            continue
        cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
        if not cells:
            continue
        lines.append("| " + " | ".join(cells) + " |")
        if len(lines) == 1:
            lines.append("|" + "|".join(["---"] * len(cells)) + "|")
    return "\n".join(lines)


# --- cache helpers ------------------------------------------------------------


def default_rules_dir() -> Path:
    """``~/.cache/wiki-translator/rules`` · honors ``XDG_CACHE_HOME`` if set."""
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".cache"
    return base / "wiki-translator" / "rules"


async def read_cache(rules_dir: Path, lang: str) -> LanguageRuleSet | None:
    """Load a cached ``LanguageRuleSet`` from disk, or ``None`` if missing/corrupt."""
    return await asyncio.to_thread(_read_sync, rules_dir, lang)


async def write_cache(rules_dir: Path, ruleset: LanguageRuleSet) -> Path:
    """Atomically write a ``LanguageRuleSet`` to ``<rules_dir>/<lang>.json``.

    Atomic via tempfile in the same directory + ``Path.replace()`` (POSIX
    rename semantics). A crash mid-write leaves a ``*.tmp`` next to the
    final path · the next successful run overwrites both.
    """
    return await asyncio.to_thread(_write_sync, rules_dir, ruleset)


def _read_sync(rules_dir: Path, lang: str) -> LanguageRuleSet | None:
    path = rules_dir / f"{lang}.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("cache read failed for %s: %s · returning None", path, exc)
        return None
    return _from_dict(payload)


def _write_sync(rules_dir: Path, ruleset: LanguageRuleSet) -> Path:
    rules_dir.mkdir(parents=True, exist_ok=True)
    final = rules_dir / f"{ruleset.lang}.json"
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=rules_dir,
        delete=False,
        suffix=".tmp",
    ) as tmp:
        json.dump(_to_dict(ruleset), tmp, ensure_ascii=False, indent=2)
        tmp_path = Path(tmp.name)
    tmp_path.replace(final)  # atomic on POSIX same-fs
    return final


def _to_dict(rs: LanguageRuleSet) -> dict[str, Any]:
    return {
        "lang": rs.lang,
        "title": rs.title,
        "url": rs.url,
        "scraped_at": rs.scraped_at.isoformat(),
        "entries": [{"grapheme": e.grapheme, "thai": e.thai, "notes": e.notes} for e in rs.entries],
        "excerpt": rs.excerpt,
    }


def _from_dict(d: Any) -> LanguageRuleSet | None:
    if not isinstance(d, dict):
        logger.warning("cache deserialize failed: payload is not a dict")
        return None
    try:
        raw_entries = d["entries"]
        if not isinstance(raw_entries, list):
            raise TypeError("entries must be a list")
        entries = tuple(
            RuleEntry(
                grapheme=str(e["grapheme"]),
                thai=str(e["thai"]),
                notes=str(e.get("notes", "")),
            )
            for e in raw_entries
            if isinstance(e, dict)
        )
        return LanguageRuleSet(
            lang=str(d["lang"]),
            title=str(d["title"]),
            url=str(d["url"]),
            scraped_at=datetime.datetime.fromisoformat(str(d["scraped_at"])),
            entries=entries,
            excerpt=str(d.get("excerpt", "")),
        )
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning("cache deserialize failed: %s", exc)
        return None
