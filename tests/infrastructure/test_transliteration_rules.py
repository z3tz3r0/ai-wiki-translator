"""Tests for `WikipediaTransliterationRuleSource` + cache helpers.

Mock-transport pattern mirrors ``tests/infrastructure/test_wikipedia_http.py``.
Each route maps a th.wiki page title to a JSON envelope wrapping HTML in
``parse.text`` (the MediaWiki API shape for ``action=parse&prop=text``).
"""

from __future__ import annotations

import datetime
import json
import logging
import os
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.application.dto import LanguageRuleSet, RuleEntry
from app.application.ports import TransliterationRuleSource
from app.infrastructure.transliteration_rules import (
    LANG_TO_TITLE,
    RulePageParseError,
    UnsupportedLanguage,
    WikipediaTransliterationRuleSource,
    default_rules_dir,
    read_cache,
    write_cache,
)


def _envelope(html: str, title: str = "x") -> dict[str, Any]:
    """JSON envelope mirroring MediaWiki ``action=parse&prop=text`` response."""
    return {"parse": {"title": title, "text": html}}


def _make_transport(routes: dict[str, dict[str, Any]]) -> httpx.MockTransport:
    """Route by ``page=`` query param → response JSON.

    Unknown pages → ``{"error": {"code": "missingtitle"}}`` so the adapter's
    null-handling path is exercised.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path != "/w/api.php":
            return httpx.Response(404, json={"error": {"code": "unknown-endpoint"}})
        page = request.url.params.get("page", "")
        body = routes.get(page)
        if body is None:
            return httpx.Response(200, json={"error": {"code": "missingtitle"}})
        return httpx.Response(200, json=body)

    return httpx.MockTransport(handler)


_EN_TITLE = LANG_TO_TITLE["en"]


# --- protocol satisfaction ---------------------------------------------------


def test_satisfies_transliteration_rule_source_protocol() -> None:
    adapter = WikipediaTransliterationRuleSource(transport=_make_transport({}))
    assert isinstance(adapter, TransliterationRuleSource)


# --- fetch happy paths -------------------------------------------------------


async def test_fetch_unknown_lang_raises_unsupported() -> None:
    adapter = WikipediaTransliterationRuleSource(transport=_make_transport({}))
    with pytest.raises(UnsupportedLanguage):
        await adapter.fetch("xx")


async def test_fetch_parses_one_wikitable_into_entries() -> None:
    html = (
        '<table class="wikitable">'
        "<tr><th>grapheme</th><th>thai</th></tr>"
        "<tr><td>a</td><td>เอ</td></tr>"
        "<tr><td>b</td><td>บี</td></tr>"
        "</table>"
    )
    adapter = WikipediaTransliterationRuleSource(
        transport=_make_transport({_EN_TITLE: _envelope(html)})
    )
    rs = await adapter.fetch("en")
    assert rs.lang == "en"
    assert rs.title == _EN_TITLE
    assert len(rs.entries) == 2
    assert rs.entries[0] == RuleEntry(grapheme="a", thai="เอ", notes="")
    assert rs.entries[1] == RuleEntry(grapheme="b", thai="บี", notes="")


async def test_fetch_handles_multiple_wikitables() -> None:
    html = (
        '<table class="wikitable"><tr><th>g</th><th>t</th></tr>'
        "<tr><td>a</td><td>เอ</td></tr></table>"
        '<table class="wikitable"><tr><th>g</th><th>t</th></tr>'
        "<tr><td>b</td><td>บี</td></tr></table>"
        '<table class="wikitable"><tr><th>g</th><th>t</th></tr>'
        "<tr><td>c</td><td>ซี</td></tr></table>"
    )
    adapter = WikipediaTransliterationRuleSource(
        transport=_make_transport({_EN_TITLE: _envelope(html)})
    )
    rs = await adapter.fetch("en")
    graphemes = [e.grapheme for e in rs.entries]
    assert graphemes == ["a", "b", "c"]


async def test_fetch_skips_rows_with_missing_cells() -> None:
    html = (
        '<table class="wikitable">'
        "<tr><th>g</th><th>t</th></tr>"
        "<tr><td>a</td><td>เอ</td></tr>"
        "<tr><td>only-one-cell</td></tr>"
        "<tr><td></td><td>เอ็มพ์ตี้</td></tr>"
        "<tr><td>c</td><td>ซี</td></tr>"
        "</table>"
    )
    adapter = WikipediaTransliterationRuleSource(
        transport=_make_transport({_EN_TITLE: _envelope(html)})
    )
    rs = await adapter.fetch("en")
    assert [e.grapheme for e in rs.entries] == ["a", "c"]


async def test_fetch_includes_notes_when_third_cell_present() -> None:
    html = (
        '<table class="wikitable">'
        "<tr><th>g</th><th>t</th><th>notes</th></tr>"
        "<tr><td>th</td><td>ธ</td><td>เสียงไม่ก้อง</td></tr>"
        "</table>"
    )
    adapter = WikipediaTransliterationRuleSource(
        transport=_make_transport({_EN_TITLE: _envelope(html)})
    )
    rs = await adapter.fetch("en")
    assert rs.entries[0].notes == "เสียงไม่ก้อง"


async def test_fetch_returns_excerpt_with_markdown_pipes() -> None:
    html = (
        '<table class="wikitable">'
        "<tr><th>g</th><th>t</th></tr>"
        "<tr><td>a</td><td>เอ</td></tr>"
        "</table>"
    )
    adapter = WikipediaTransliterationRuleSource(
        transport=_make_transport({_EN_TITLE: _envelope(html)})
    )
    rs = await adapter.fetch("en")
    assert "|" in rs.excerpt
    assert "เอ" in rs.excerpt


# --- fetch error paths -------------------------------------------------------


async def test_fetch_raises_on_zero_entries() -> None:
    """Empty wikitable → ``RulePageParseError`` (page layout broke)."""
    html = '<table class="wikitable"><tr><th>g</th><th>t</th></tr></table>'
    adapter = WikipediaTransliterationRuleSource(
        transport=_make_transport({_EN_TITLE: _envelope(html)})
    )
    with pytest.raises(RulePageParseError):
        await adapter.fetch("en")


async def test_fetch_raises_on_no_tables_at_all() -> None:
    html = "<p>no tables here</p>"
    adapter = WikipediaTransliterationRuleSource(
        transport=_make_transport({_EN_TITLE: _envelope(html)})
    )
    with pytest.raises(RulePageParseError):
        await adapter.fetch("en")


async def test_fetch_raises_when_api_returns_error() -> None:
    """``parse.error`` from MediaWiki → ``RulePageParseError`` (no parse.text)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"error": {"code": "missingtitle"}})

    adapter = WikipediaTransliterationRuleSource(transport=httpx.MockTransport(handler))
    with pytest.raises(RulePageParseError):
        await adapter.fetch("en")


async def test_fetch_raises_on_5xx() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="Service Unavailable")

    adapter = WikipediaTransliterationRuleSource(transport=httpx.MockTransport(handler))
    with pytest.raises(httpx.HTTPStatusError):
        await adapter.fetch("en")


# --- cache roundtrip ---------------------------------------------------------


def _sample_ruleset(lang: str = "en") -> LanguageRuleSet:
    return LanguageRuleSet(
        lang=lang,
        title="dummy/title",
        url="https://example/wiki/dummy",
        scraped_at=datetime.datetime(2026, 5, 4, 12, 0, 0),
        entries=(
            RuleEntry(grapheme="a", thai="เอ", notes=""),
            RuleEntry(grapheme="b", thai="บี", notes="optional notes"),
        ),
        excerpt="| a | เอ |\n| b | บี |",
    )


async def test_cache_roundtrip(tmp_path: Path) -> None:
    rs = _sample_ruleset()
    path = await write_cache(tmp_path, rs)
    assert path.is_file()
    loaded = await read_cache(tmp_path, "en")
    assert loaded == rs


async def test_cache_read_missing_returns_none(tmp_path: Path) -> None:
    assert await read_cache(tmp_path, "xx") is None


async def test_cache_read_corrupt_json_returns_none(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    corrupt = tmp_path / "en.json"
    corrupt.write_text("{not valid json", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        result = await read_cache(tmp_path, "en")
    assert result is None
    assert any("cache read failed" in rec.message for rec in caplog.records)


async def test_cache_read_partial_json_returns_none(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Valid JSON but missing required keys → None + warning logged."""
    bad = tmp_path / "en.json"
    bad.write_text(json.dumps({"lang": "en"}), encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        result = await read_cache(tmp_path, "en")
    assert result is None
    assert any("cache deserialize failed" in rec.message for rec in caplog.records)


async def test_cache_write_creates_parent_dirs(tmp_path: Path) -> None:
    nested = tmp_path / "a" / "b" / "c"
    rs = _sample_ruleset()
    path = await write_cache(nested, rs)
    assert path.parent == nested
    assert path.is_file()


async def test_cache_write_cleans_tmp_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the rename step raises, the tempfile must not leak."""

    def boom(self: Path, target: Path) -> None:
        raise OSError("simulated cross-device rename failure")

    monkeypatch.setattr(Path, "replace", boom)
    rs = _sample_ruleset()
    with pytest.raises(OSError):
        await write_cache(tmp_path, rs)
    leftovers = list(tmp_path.glob("*.tmp"))  # noqa: ASYNC240 — test inspection
    assert leftovers == []


async def test_cache_read_lang_mismatch_returns_none(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """File named en.json with lang=de inside must be rejected · phase 2 safety."""
    payload = {
        "lang": "de",
        "title": "wrong-lang-inside-en-file",
        "url": "https://x",
        "scraped_at": "2026-05-04T12:00:00",
        "entries": [{"grapheme": "a", "thai": "เอ", "notes": ""}],
        "excerpt": "",
    }
    (tmp_path / "en.json").write_text(json.dumps(payload), encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        result = await read_cache(tmp_path, "en")
    assert result is None
    assert any("lang mismatch" in rec.message for rec in caplog.records)


async def test_cache_write_overwrites_existing_atomically(tmp_path: Path) -> None:
    rs1 = _sample_ruleset()
    await write_cache(tmp_path, rs1)
    rs2 = LanguageRuleSet(
        lang="en",
        title="updated",
        url="https://x",
        scraped_at=datetime.datetime(2026, 6, 1),
        entries=(RuleEntry(grapheme="z", thai="ซี", notes=""),),
        excerpt="| z | ซี |",
    )
    await write_cache(tmp_path, rs2)
    loaded = await read_cache(tmp_path, "en")
    assert loaded is not None
    assert loaded.title == "updated"
    leftovers = list(tmp_path.glob("*.tmp"))  # noqa: ASYNC240 — test inspection, not hot-path IO
    assert leftovers == []


# --- default_rules_dir -------------------------------------------------------


def test_default_rules_dir_honors_xdg_cache_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    assert default_rules_dir() == tmp_path / "wiki-translator" / "rules"


def test_default_rules_dir_falls_back_to_home_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    expected = Path.home() / ".cache" / "wiki-translator" / "rules"
    assert default_rules_dir() == expected


# --- integration -------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("CI") is not None,
    reason="integration tests hit live th.wiki · run locally with `pytest -m integration`",
)
async def test_integration_fetch_against_live_th_wiki_en() -> None:
    adapter = WikipediaTransliterationRuleSource()
    rs = await adapter.fetch("en")
    assert rs.lang == "en"
    assert len(rs.entries) >= 10
    assert rs.excerpt
