"""Mechanical checks on a Thai wikitext draft, so the reviewer only reads what needs judgment.

Usage (repo root, stdlib only):
  python -X utf8 -I check_wikitext.py DRAFT.wikitext [--source SOURCE.wikitext]
         [--signs ai_signs_th.txt]

Reports, with line numbers:
  * markup balance: {{ }}, [[ ]], <ref> open/close, named refs reused but never defined
  * heading levels (level 1, skipped levels) and bold outside the lead
  * em dashes (U+2014) and Markdown leftovers (**, ##, ```), which never belong here
  * en dashes (U+2013) outside ranges and pairs: th.wiki style allows them only there
  * long lines that are still mostly Latin script (untranslated English)
  * phrases from the signs list: STRONG, MOS, SIGN and RAW ones always (RAW scans refs and
    URLs too), SOFT ones only when frequent
  * with --source: numbers (years, quantities) in the source but missing from the draft,
    and the <ref> count on each side
Exit code 0 always · this is a report, the reviewer decides.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

DEFAULT_SIGNS = Path(__file__).with_name("ai_signs_th.txt")
SOFT_MIN_HITS = 3
LATIN_SHARE = 0.4
LATIN_MIN_LETTERS = 40
MAX_LISTED = 40
REF_OPEN = re.compile(r"<ref(?:\s[^>]*)?(?<!/)>", re.I)
REF_SELF = re.compile(r"<ref[^>]*/>", re.I)
REF_CLOSE = re.compile(r"</ref>", re.I)
REF_BLOCK = re.compile(r"<ref[^>/]*>.*?</ref>|<ref[^>]*/>", re.S | re.I)
TEMPLATE = re.compile(r"\{\{[^{}]*\}\}")
LINK_TARGET = re.compile(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]")
NUMBER = re.compile(r"(?<![\w.])\d[\d,.]*\d(?![\w])|(?<![\w.])\d(?![\w.])")
MARKDOWN = re.compile(r"\*\*[^*\n]+\*\*|^#{1,6}\s|```", re.M)
EM_DASH = re.compile("\u2014")
# a range or pair: after a digit (1953\u20132008, 1999 \u2013 ...) or unspaced between words
EN_DASH_ALLOWED = re.compile(r"(?<=\d)\s?\u2013|(?<=\S)\u2013(?=\S)")
HEADING = re.compile(r"^(=+)[^=].*?[^=](=+)\s*$")
BOLD = re.compile(r"'''[^']+'''")
ALWAYS = ("strong", "mos", "sign", "raw")  # buckets reported on every hit
RAW = "raw"  # scanned on raw wikitext, refs and URLs included


def load_signs(path: Path) -> dict[str, list[str]]:
    """Parse the signs file into buckets (`[strong]`, `[mos]`, `[sign]`, `[raw]`, `[soft]`).

    `#` starts a comment line.
    """
    buckets: dict[str, list[str]] = {name: [] for name in (*ALWAYS, "soft")}
    current = "strong"
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        name = line[1:-1] if line.startswith("[") and line.endswith("]") else None
        if name in buckets:
            current = name
        else:
            buckets[current].append(line)
    return buckets


def prose(text: str) -> str:
    """Wikitext with refs, templates and link targets removed, for language checks."""
    out = REF_BLOCK.sub("", text)
    for _ in range(3):  # nested templates peel from the inside out
        out = TEMPLATE.sub("", out)
    return LINK_TARGET.sub(r"\1", out)


def balance(text: str) -> list[str]:
    issues = []
    for opener, closer in (("{{", "}}"), ("[[", "]]")):
        if text.count(opener) != text.count(closer):
            issues.append(f"{opener} x{text.count(opener)} vs {closer} x{text.count(closer)}")
    opened, closed = len(REF_OPEN.findall(text)), len(REF_CLOSE.findall(text))
    if opened != closed:
        issues.append(f"<ref> open x{opened} vs </ref> x{closed}")
    return issues


REF_NAME = re.compile(r"""<ref\s[^>]*name\s*=\s*["']?([^"'/>]+?)["']?\s*(/?)>""", re.I)


def undefined_named_refs(text: str) -> list[str]:
    """Named refs reused (``<ref name=x />``) but never defined with content."""
    defined, reused = set(), set()
    for name, self_closing in REF_NAME.findall(text):
        (reused if self_closing else defined).add(name.strip())
    return sorted(reused - defined)


def heading_issues(lines: list[str]) -> list[str]:
    """Level-1 headings and skipped levels, both Markdown-conversion leftovers."""
    issues, previous = [], 1
    for n, line in enumerate(lines, 1):
        match = HEADING.match(line)
        if not match:
            continue
        level = min(len(match.group(1)), len(match.group(2)))
        if level == 1:
            issues.append(f"L{n} level-1 heading")
        elif level > previous + 1:
            issues.append(f"L{n} jumps from level {previous} to {level}")
        previous = level
    return issues


def bold_outside_lead(lines: list[str]) -> list[int]:
    """Lines after the first heading that use bold: the lead bolds the title, prose should not."""
    first = next((n for n, line in enumerate(lines, 1) if HEADING.match(line)), len(lines) + 1)
    return [n for n, line in enumerate(lines, 1) if n > first and BOLD.search(line)]


def stray_en_dashes(lines: list[str]) -> list[int]:
    """Lines with an en dash used as sentence punctuation rather than in a range or pair."""
    return [n for n, line in enumerate(lines, 1) if "\u2013" in EN_DASH_ALLOWED.sub("", line)]


def line_hits(lines: list[str], pattern: re.Pattern[str]) -> list[int]:
    return [n for n, line in enumerate(lines, 1) if pattern.search(line)]


def latin_lines(lines: list[str]) -> list[int]:
    hits = []
    for n, line in enumerate(lines, 1):
        letters = [c for c in prose(line) if c.isalpha()]
        latin = sum(1 for c in letters if c.isascii())
        if len(letters) >= LATIN_MIN_LETTERS and latin / len(letters) > LATIN_SHARE:
            hits.append(n)
    return hits


def hits(phrase: str, text: str) -> int:
    """Occurrences of a phrase, or of a regex when the entry starts with ``re:``.

    Thai has no spaces between words, so a plain phrase can sit inside a longer word
    (ชัดเจนว่า inside ไม่ชัดเจนว่า). Regex entries exclude those with lookarounds.
    """
    if phrase.startswith("re:"):
        return len(re.findall(phrase[3:], text))
    return text.count(phrase)


def label(phrase: str) -> str:
    return phrase[3:] if phrase.startswith("re:") else phrase


def sign_report(lines: list[str], buckets: dict[str, list[str]]) -> list[str]:
    texts = [prose(line) for line in lines]
    out = []
    for bucket in ALWAYS:
        scanned = lines if bucket == RAW else texts
        for phrase in buckets.get(bucket, []):
            found = [n for n, text in enumerate(scanned, 1) if hits(phrase, text)]
            if found:
                out.append(f"{bucket.upper()} «{label(phrase)}» lines {found}")
    counts: Counter[str] = Counter()
    for text in texts:
        for phrase in buckets.get("soft", []):
            counts[label(phrase)] += hits(phrase, text)
    out.extend(f"SOFT «{p}» x{c}" for p, c in counts.most_common() if c >= SOFT_MIN_HITS)
    return out


def number_gap(draft: str, source: str) -> list[str]:
    def numbers(text: str) -> Counter[str]:
        return Counter(n.replace(",", "") for n in NUMBER.findall(prose(text)))

    missing = numbers(source) - numbers(draft)
    # single digits match too much to mean anything
    meaningful = [n for n in missing if len(n.replace(".", "")) >= 2]
    ranked = sorted(meaningful, key=lambda n: (-len(n), n))
    if len(ranked) > MAX_LISTED:
        return [*ranked[:MAX_LISTED], f"+{len(ranked) - MAX_LISTED} more"]
    return ranked


def report(draft_path: Path, source_path: Path | None, signs_path: Path) -> str:
    draft = draft_path.read_text(encoding="utf-8")
    lines = draft.splitlines()
    buckets = load_signs(signs_path) if signs_path.is_file() else {}
    out = [f"# check_wikitext · {draft_path.name} · {len(lines)} lines"]
    out.append("balance: " + ("; ".join(balance(draft)) or "ok"))
    out.append(f"named refs reused but never defined: {undefined_named_refs(draft) or 'none'}")
    out.append(f"em dashes (U+2014): lines {line_hits(lines, EM_DASH) or 'none'}")
    out.append(f"en dashes outside ranges (rephrase): lines {stray_en_dashes(lines) or 'none'}")
    out.append(f"markdown leftovers: lines {line_hits(lines, MARKDOWN) or 'none'}")
    out.append("headings: " + ("; ".join(heading_issues(lines)) or "ok"))
    out.append(f"bold outside the lead: lines {bold_outside_lead(lines) or 'none'}")
    out.append(f"mostly-Latin lines: {latin_lines(lines) or 'none'}")
    signs = sign_report(lines, buckets)
    out.append("ai signs: " + ("none" if not signs else ""))
    out.extend(f"  {s}" for s in signs)
    if source_path is not None:
        source = source_path.read_text(encoding="utf-8")
        refs = (
            len(REF_OPEN.findall(source)) + len(REF_SELF.findall(source)),
            len(REF_OPEN.findall(draft)) + len(REF_SELF.findall(draft)),
        )
        out.append(f"refs: source {refs[0]} · draft {refs[1]}")
        gap = number_gap(draft, source)
        out.append(f"numbers in source missing from draft: {gap or 'none'}")
    return "\n".join(out)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("draft", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--signs", type=Path, default=DEFAULT_SIGNS)
    args = parser.parse_args(argv)
    print(report(args.draft, args.source, args.signs))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
