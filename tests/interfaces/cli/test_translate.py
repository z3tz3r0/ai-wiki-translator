"""Tests for `wiki-translate` CLI command."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from app.application.dto import (
    Draft,
    SourceScore,
    TranslateArticleCommand,
    ValidationResult,
)
from app.interfaces.cli import main as cli_main


def _passing_draft(slug: str = "demo", source_lang: str = "en") -> Draft:
    score = SourceScore(
        lang=source_lang,
        word_count=1234,
        ref_count=8,
        locale_match=True,
        winning_signal="locale",
    )
    return Draft(
        slug=slug,
        source_lang=source_lang,
        source_score=score,
        validation=ValidationResult(passed=True, reasons=()),
        wikitext="paste-ready translated wikitext",
        review_md="# Review\n\nlooks good",
    )


def _rejected_draft(slug: str = "bad") -> Draft:
    score = SourceScore(
        lang="en",
        word_count=12,
        ref_count=0,
        locale_match=False,
        winning_signal="fallback_en",
    )
    return Draft(
        slug=slug,
        source_lang="en",
        source_score=score,
        validation=ValidationResult(
            passed=False,
            reasons=("word count 12 below threshold 500",),
        ),
        wikitext="",
        review_md="# Review\n\nrejected",
    )


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_translate_passes_title_to_use_case(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, TranslateArticleCommand] = {}

    class FakeUseCase:
        async def execute(self, cmd: TranslateArticleCommand) -> Draft:
            captured["cmd"] = cmd
            return _passing_draft()

    monkeypatch.setattr(
        cli_main.bootstrap,
        "build_translate_use_case",
        lambda **_: FakeUseCase(),
    )
    result = runner.invoke(cli_main.translate_app, ["My Article"])
    assert result.exit_code == 0, result.output
    assert captured["cmd"].title == "My Article"
    assert captured["cmd"].source_lang_override is None
    assert captured["cmd"].glossary_path is None


def test_translate_passes_source_lang_override(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, TranslateArticleCommand] = {}

    class FakeUseCase:
        async def execute(self, cmd: TranslateArticleCommand) -> Draft:
            captured["cmd"] = cmd
            return _passing_draft()

    monkeypatch.setattr(cli_main.bootstrap, "build_translate_use_case", lambda **_: FakeUseCase())
    result = runner.invoke(cli_main.translate_app, ["My Article", "--source-lang", "ja"])
    assert result.exit_code == 0, result.output
    assert captured["cmd"].source_lang_override == "ja"


def test_translate_passes_glossary_path(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    glossary_file = tmp_path / "g.txt"
    glossary_file.write_text("Foo:ฟู\n", encoding="utf-8")
    captured: dict[str, TranslateArticleCommand] = {}

    class FakeUseCase:
        async def execute(self, cmd: TranslateArticleCommand) -> Draft:
            captured["cmd"] = cmd
            return _passing_draft()

    monkeypatch.setattr(cli_main.bootstrap, "build_translate_use_case", lambda **_: FakeUseCase())
    result = runner.invoke(cli_main.translate_app, ["X", "--glossary", str(glossary_file)])
    assert result.exit_code == 0, result.output
    assert captured["cmd"].glossary_path == str(glossary_file)


def test_translate_routes_output_dir_to_bootstrap(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured_kwargs: dict[str, Any] = {}

    class FakeUseCase:
        async def execute(self, cmd: TranslateArticleCommand) -> Draft:
            return _passing_draft()

    def fake_build(**kwargs: Any) -> FakeUseCase:
        captured_kwargs.update(kwargs)
        return FakeUseCase()

    monkeypatch.setattr(cli_main.bootstrap, "build_translate_use_case", fake_build)
    result = runner.invoke(cli_main.translate_app, ["X", "--output-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert captured_kwargs["output_dir"] == tmp_path


def test_translate_prints_passing_summary(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    draft = _passing_draft(slug="my-article", source_lang="en")

    class FakeUseCase:
        async def execute(self, cmd: TranslateArticleCommand) -> Draft:
            return draft

    monkeypatch.setattr(cli_main.bootstrap, "build_translate_use_case", lambda **_: FakeUseCase())
    result = runner.invoke(cli_main.translate_app, ["My Article"])
    assert result.exit_code == 0, result.output
    assert "my-article" in result.output
    assert "en" in result.output
    assert "passed" in result.output.lower()
    assert "1234" in result.output
    assert "8" in result.output


def test_translate_prints_rejection_reasons(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    draft = _rejected_draft()

    class FakeUseCase:
        async def execute(self, cmd: TranslateArticleCommand) -> Draft:
            return draft

    monkeypatch.setattr(cli_main.bootstrap, "build_translate_use_case", lambda **_: FakeUseCase())
    result = runner.invoke(cli_main.translate_app, ["Bad Article"])
    assert result.exit_code == 0, result.output
    assert "rejected" in result.output.lower()
    assert "word count 12 below threshold 500" in result.output


def test_translate_use_case_exception_returns_nonzero(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    class BoomUseCase:
        async def execute(self, cmd: TranslateArticleCommand) -> Draft:
            raise RuntimeError("rpc blew up")

    monkeypatch.setattr(cli_main.bootstrap, "build_translate_use_case", lambda **_: BoomUseCase())
    result = runner.invoke(cli_main.translate_app, ["X"])
    assert result.exit_code != 0
    assert "rpc blew up" in result.output


def test_translate_bootstrap_failure_prints_friendly_error(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Missing-credential path: bootstrap raises, user sees a one-line message."""

    def explode(**_: Any) -> Any:
        raise RuntimeError("GEMINI_API_KEY is required · export it before running")

    monkeypatch.setattr(cli_main.bootstrap, "build_translate_use_case", explode)
    result = runner.invoke(cli_main.translate_app, ["X"])
    assert result.exit_code == 1
    assert "GEMINI_API_KEY" in result.output


def test_translate_help_does_not_call_bootstrap(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--help` must not trigger bootstrap (no API keys needed for help)."""

    def fail(**_: Any) -> Any:
        pytest.fail("bootstrap should not be called for --help")

    monkeypatch.setattr(cli_main.bootstrap, "build_translate_use_case", fail)
    result = runner.invoke(cli_main.translate_app, ["--help"])
    assert result.exit_code == 0
    assert "title" in result.output.lower()
