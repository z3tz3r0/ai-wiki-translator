"""outline.py · section split, extraction and the per-section signals."""

from __future__ import annotations

from pathlib import Path
from types import ModuleType

import pytest

ARTICLE = """{{Infobox|year=1999}}
Lead text in 2005.<ref>{{cite web|date=2026}}</ref>
== <!-- linked from ODP --> History ==
Started 2001.
=== Early ===
Draft in 2002.<ref name="a">x</ref>
== Adoption ==
Used 2021, cited <ref name="a" />.
"""


def test_split_keeps_lead_levels_and_strips_heading_comments(outline: ModuleType) -> None:
    sections = outline.split_sections(ARTICLE)
    assert [(s.level, s.heading) for s in sections] == [
        (0, "(lead)"),
        (2, "History"),
        (3, "Early"),
        (2, "Adoption"),
    ]


def test_latest_year_ignores_references_and_citations(outline: ModuleType) -> None:
    lead = outline.split_sections(ARTICLE)[0]
    assert lead.latest_year == "2005"  # 2026 sits inside the citation


def test_refs_count_opening_and_reused_refs(outline: ModuleType) -> None:
    sections = outline.split_sections(ARTICLE)
    assert [s.refs for s in sections] == [1, 0, 1, 1]


def test_extract_returns_section_with_subsections_only(outline: ModuleType) -> None:
    body = outline.extract(outline.split_sections(ARTICLE), "history")
    assert body is not None
    assert "Early" in body
    assert "Adoption" not in body


def test_extract_unknown_heading_returns_none(outline: ModuleType) -> None:
    assert outline.extract(outline.split_sections(ARTICLE), "Nope") is None


def test_outline_from_file_prints_one_row_per_section(
    outline: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "a.wikitext"
    path.write_text(ARTICLE, encoding="utf-8")
    assert outline.main([str(path)]) == 0
    rows = capsys.readouterr().out.splitlines()
    assert len(rows) == 2 + 4  # header, column names, four sections
