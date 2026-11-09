"""Flag th.wiki policy pages edited since the revision the rules were written from.

Usage (repo root): python -X utf8 -I .claude/skills/thwiki-rules/scripts/check_sources.py
Reads ../sources.tsv (title, revid read, date read, why). For each changed page prints
the revid range and a compare URL, so only the diff gets read, never the whole page.
"""

from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

UA = "ai-wiki-translator/0.1 (https://github.com/z3tz3r0/ai-wiki-translator)"
API = "https://th.wikipedia.org/w/api.php"
SOURCES = Path(__file__).resolve().parent.parent / "sources.tsv"
BATCH = 50  # API limit for titles per query


def read_sources() -> dict[str, int]:
    rows = {}
    for line in SOURCES.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        title, revid, *_ = line.split("\t")
        rows[title] = int(revid)
    return rows


def current_revids(titles: list[str]) -> dict[str, int]:
    found: dict[str, int] = {}
    for start in range(0, len(titles), BATCH):
        params = {
            "action": "query",
            "titles": "|".join(titles[start : start + BATCH]),
            "prop": "revisions",
            "rvprop": "ids",
            "format": "json",
            "formatversion": "2",
        }
        req = urllib.request.Request(  # noqa: S310 · fixed https URL, only the query varies
            f"{API}?{urllib.parse.urlencode(params)}", headers={"User-Agent": UA}
        )
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 · fixed https URL, only the query varies
            pages = json.loads(resp.read().decode("utf-8"))["query"]["pages"]
        for page in pages:
            if "revisions" in page:
                found[page["title"]] = page["revisions"][0]["revid"]
    return found


def main() -> int:
    known = read_sources()
    live = current_revids(list(known))
    changed = 0
    for title, old in known.items():
        new = live.get(title)
        if new is None:
            print(f"MISSING  {title}")
            changed += 1
        elif new != old:
            url = f"https://th.wikipedia.org/w/index.php?diff={new}&oldid={old}"
            print(f"CHANGED  {title}  {old} -> {new}  {url}")
            changed += 1
    print(f"{len(known) - changed}/{len(known)} rule sources unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
