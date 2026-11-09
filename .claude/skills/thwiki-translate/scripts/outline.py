"""Section outline of Wikipedia articles, and section extraction, without reading whole texts.

Usage (run from the repo root, plain python, stdlib only):
  python -X utf8 -I outline.py th:โอเพนด็อกคิวเมนต์ en:OpenDocument [--save DIR]
  python -X utf8 -I outline.py path/to/file.wikitext [--extract "Heading" ...]

A source is `<lang>:<title>` (fetched live from <lang>.wikipedia.org) or a file path.
The outline lists, per section: index, heading level, characters, <ref> count and the
latest year mentioned outside references (a cheap "how current is this" signal).
`--save DIR` writes each fetched article to DIR/<lang>-<title>.wikitext plus its revision id
in the first line of the outline, so later `--extract` calls read the file, not the network.
`--extract` prints one section (with its subsections) from a single source.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

UA = "ai-wiki-translator/0.1 (https://github.com/z3tz3r0/ai-wiki-translator)"
HEADING = re.compile(r"^(={2,6})\s*(.+?)\s*\1\s*$")
REF_BLOCK = re.compile(r"<ref[^>/]*>.*?</ref>|<ref[^>]*/>", re.S | re.I)
TEMPLATE_CITE = re.compile(r"\{\{\s*(cite|citation|อ้างอิง)[^{}]*\}\}", re.I)
YEAR = re.compile(r"(?<!\d)(1[5-9]\d\d|20\d\d)(?!\d)")
COMMENT = re.compile(r"<!--.*?-->", re.S)
REF_OPEN = re.compile(r"<ref[\s>/]", re.I)


@dataclass(frozen=True)
class Section:
    index: int
    level: int
    heading: str
    text: str

    @property
    def refs(self) -> int:
        return len(REF_OPEN.findall(self.text))

    @property
    def latest_year(self) -> str:
        body = TEMPLATE_CITE.sub("", REF_BLOCK.sub("", self.text))
        years = YEAR.findall(body)
        return max(years) if years else "-"


@dataclass(frozen=True)
class Source:
    label: str
    wikitext: str
    meta: str


def split_sections(wikitext: str) -> list[Section]:
    sections: list[Section] = []
    level, heading, buf = 0, "(lead)", []
    for line in wikitext.splitlines():
        match = HEADING.match(line)
        if match:
            sections.append(Section(len(sections), level, heading, "\n".join(buf)))
            heading = COMMENT.sub("", match.group(2)).strip()
            level, buf = len(match.group(1)), [line]
        else:
            buf.append(line)
    sections.append(Section(len(sections), level, heading, "\n".join(buf)))
    return sections


def extract(sections: list[Section], heading: str) -> str | None:
    """Return the section titled ``heading`` plus its subsections, or None."""
    wanted = heading.strip().casefold()
    for i, sec in enumerate(sections):
        if sec.heading.strip().casefold() != wanted:
            continue
        parts = [sec.text]
        for nxt in sections[i + 1 :]:
            if nxt.level <= sec.level:
                break
            parts.append(nxt.text)
        return "\n".join(parts)
    return None


def fetch(lang: str, title: str) -> Source:
    params = {
        "action": "query",
        "titles": title,
        "redirects": "1",
        "prop": "revisions",
        "rvprop": "ids|timestamp|content",
        "rvslots": "main",
        "format": "json",
        "formatversion": "2",
    }
    url = f"https://{lang}.wikipedia.org/w/api.php?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})  # noqa: S310 · fixed https URL, only the query varies
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 · fixed https URL, only the query varies
        page = json.loads(resp.read().decode("utf-8"), strict=False)["query"]["pages"][0]
    if page.get("missing"):
        raise SystemExit(f"{lang}:{title} does not exist")
    rev = page["revisions"][0]
    text = rev["slots"]["main"]["content"]
    meta = f"rev {rev['revid']} · {rev['timestamp'][:10]} · {len(text.encode('utf-8'))} bytes"
    return Source(f"{lang}:{page['title']}", text, meta)


def load(spec: str) -> Source:
    path = Path(spec)
    if path.is_file():
        return Source(path.name, path.read_text(encoding="utf-8"), "file")
    lang, sep, title = spec.partition(":")
    if not sep or not re.fullmatch(r"[a-z\-]{2,12}", lang):
        raise SystemExit(f"not a file and not <lang>:<title>: {spec}")
    return fetch(lang, title)


def render_outline(src: Source) -> str:
    rows = [f"== {src.label} · {src.meta}", "   #  lvl  chars  refs  year  heading"]
    for sec in split_sections(src.wikitext):
        indent = "  " * max(sec.level - 2, 0)
        rows.append(
            f"{sec.index:>4}  {sec.level:>3}  {len(sec.text):>5}  {sec.refs:>4}  "
            f"{sec.latest_year:>4}  {indent}{sec.heading}"
        )
    return "\n".join(rows)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("sources", nargs="+", help="<lang>:<title> or a .wikitext file")
    parser.add_argument("--extract", action="append", default=[], help="heading to print")
    parser.add_argument("--save", type=Path, help="directory for fetched wikitext")
    args = parser.parse_args(argv)
    if args.extract and len(args.sources) != 1:
        parser.error("--extract needs exactly one source")
    for spec in args.sources:
        src = load(spec)
        if args.save and src.meta != "file":
            args.save.mkdir(parents=True, exist_ok=True)
            safe = re.sub(r'[\\/:*?"<>|]', "_", src.label)
            (args.save / f"{safe}.wikitext").write_text(src.wikitext, encoding="utf-8")
        if not args.extract:
            print(render_outline(src))
            continue
        sections = split_sections(src.wikitext)
        for heading in args.extract:
            body = extract(sections, heading)
            print(body if body is not None else f"!! no section titled {heading!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
