"""Tests for `RefreshRulesUseCase` orchestration with `FakeTransliterationRuleSource`."""

from __future__ import annotations

import datetime
import json
from pathlib import Path

import pytest

from app.application.dto import LanguageRuleSet, RuleEntry
from app.application.use_cases.refresh_rules import RefreshRulesUseCase
from app.infrastructure.transliteration_rules import (
    RulePageParseError,
    UnsupportedLanguage,
)
from tests.fakes.transliteration import FakeTransliterationRuleSource


def _ruleset(lang: str) -> LanguageRuleSet:
    return LanguageRuleSet(
        lang=lang,
        title=f"title-{lang}",
        url=f"https://x/{lang}",
        scraped_at=datetime.datetime(2026, 5, 4, 12, 0, 0),
        entries=(RuleEntry(grapheme="a", thai="เอ", notes=""),),
        excerpt="x",
    )


async def test_execute_writes_cache_for_each_lang(tmp_path: Path) -> None:
    fake = FakeTransliterationRuleSource(results={"en": _ruleset("en"), "fr": _ruleset("fr")})
    use_case = RefreshRulesUseCase(source=fake, rules_dir=tmp_path)
    results = await use_case.execute(["en", "fr"])
    assert all(r.ok for r in results)
    assert (tmp_path / "en.json").is_file()
    assert (tmp_path / "fr.json").is_file()


async def test_execute_swallows_unsupported_language_and_continues(
    tmp_path: Path,
) -> None:
    fake = FakeTransliterationRuleSource(
        results={"en": _ruleset("en")},
        raises={"xx": UnsupportedLanguage("no rule page for xx")},
    )
    use_case = RefreshRulesUseCase(source=fake, rules_dir=tmp_path)
    results = await use_case.execute(["en", "xx"])
    assert [r.ok for r in results] == [True, False]
    assert results[1].error is not None
    assert (tmp_path / "en.json").is_file()
    assert not (tmp_path / "xx.json").exists()


async def test_execute_swallows_parse_error_and_continues(tmp_path: Path) -> None:
    fake = FakeTransliterationRuleSource(
        results={"en": _ruleset("en")},
        raises={"de": RulePageParseError("page layout broke")},
    )
    use_case = RefreshRulesUseCase(source=fake, rules_dir=tmp_path)
    results = await use_case.execute(["de", "en"])
    assert results[0].ok is False
    assert results[1].ok is True
    assert "page layout broke" in (results[0].error or "")


async def test_execute_propagates_oserror_from_disk(tmp_path: Path) -> None:
    """``OSError`` during write must propagate (not be swallowed)."""
    fake = FakeTransliterationRuleSource(results={"en": _ruleset("en")})
    parent = tmp_path / "ro"
    parent.mkdir()
    parent.chmod(0o500)  # read-only · child mkdir + write fail
    try:
        use_case = RefreshRulesUseCase(source=fake, rules_dir=parent / "child")
        with pytest.raises(OSError):
            await use_case.execute(["en"])
    finally:
        parent.chmod(0o700)


async def test_execute_returns_results_in_input_order(tmp_path: Path) -> None:
    fake = FakeTransliterationRuleSource(
        results={
            "en": _ruleset("en"),
            "de": _ruleset("de"),
            "fr": _ruleset("fr"),
        }
    )
    use_case = RefreshRulesUseCase(source=fake, rules_dir=tmp_path)
    results = await use_case.execute(["fr", "en", "de"])
    assert [r.lang for r in results] == ["fr", "en", "de"]


async def test_cache_json_has_expected_shape(tmp_path: Path) -> None:
    """Sanity-check the JSON shape written by the use case."""
    fake = FakeTransliterationRuleSource(results={"en": _ruleset("en")})
    use_case = RefreshRulesUseCase(source=fake, rules_dir=tmp_path)
    await use_case.execute(["en"])
    data = json.loads((tmp_path / "en.json").read_text(encoding="utf-8"))
    assert set(data.keys()) >= {
        "lang",
        "title",
        "url",
        "scraped_at",
        "entries",
        "excerpt",
    }
    assert data["lang"] == "en"
    assert isinstance(data["entries"], list)
    assert data["entries"][0]["grapheme"] == "a"
    assert data["entries"][0]["thai"] == "เอ"
