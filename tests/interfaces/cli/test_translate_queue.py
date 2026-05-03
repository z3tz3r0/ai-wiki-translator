"""Tests for `wiki-translate-queue` CLI command."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from app.application.dto import (
    Draft,
    SourceScore,
    TranslateArticleCommand,
    ValidationResult,
)
from app.interfaces.cli import main as cli_main


def _draft(slug: str, *, passed: bool = True) -> Draft:
    score = SourceScore(
        lang="en",
        word_count=1000 if passed else 12,
        ref_count=5 if passed else 0,
        locale_match=False,
        winning_signal="fallback_en",
    )
    return Draft(
        slug=slug,
        source_lang="en",
        source_score=score,
        validation=ValidationResult(
            passed=passed,
            reasons=() if passed else ("source too short",),
        ),
        wikitext="..." if passed else "",
        review_md="# r",
    )


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_queue_runs_each_entry_in_order(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    queue_file = tmp_path / "queue.toml"
    queue_file.write_text(
        '[[entry]]\ntitle = "Article A"\n\n[[entry]]\ntitle = "Article B"\n',
        encoding="utf-8",
    )
    seen: list[str] = []

    class FakeUseCase:
        async def execute(self, cmd: TranslateArticleCommand) -> Draft:
            seen.append(cmd.title)
            return _draft(slug=cmd.title.lower().replace(" ", "-"))

    monkeypatch.setattr(cli_main.bootstrap, "build_translate_use_case", lambda **_: FakeUseCase())
    result = runner.invoke(cli_main.translate_queue_app, ["--config", str(queue_file)])
    assert result.exit_code == 0, result.output
    assert seen == ["Article A", "Article B"]
    assert "article-a" in result.output
    assert "article-b" in result.output


def test_queue_falls_back_to_default_path_when_no_config(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    default_path = tmp_path / "default-queue.toml"
    default_path.write_text('[[entry]]\ntitle = "Default"\n', encoding="utf-8")
    monkeypatch.setattr(cli_main, "_DEFAULT_QUEUE_PATH", default_path)
    seen: list[str] = []

    class FakeUseCase:
        async def execute(self, cmd: TranslateArticleCommand) -> Draft:
            seen.append(cmd.title)
            return _draft(slug="default")

    monkeypatch.setattr(cli_main.bootstrap, "build_translate_use_case", lambda **_: FakeUseCase())
    result = runner.invoke(cli_main.translate_queue_app, [])
    assert result.exit_code == 0, result.output
    assert seen == ["Default"]


def test_queue_missing_config_exits_nonzero(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    nonexistent = tmp_path / "nope.toml"
    monkeypatch.setattr(cli_main, "_DEFAULT_QUEUE_PATH", nonexistent)
    result = runner.invoke(cli_main.translate_queue_app, [])
    assert result.exit_code != 0
    assert "not found" in result.output.lower() or "nope.toml" in result.output


def test_queue_malformed_toml_exits_nonzero(runner: CliRunner, tmp_path: Path) -> None:
    bad_file = tmp_path / "bad.toml"
    bad_file.write_text("not = valid = toml\n", encoding="utf-8")
    result = runner.invoke(cli_main.translate_queue_app, ["--config", str(bad_file)])
    assert result.exit_code != 0


def test_queue_empty_file_runs_zero_translations(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    empty_file = tmp_path / "empty.toml"
    empty_file.write_text("", encoding="utf-8")
    seen: list[str] = []

    class FakeUseCase:
        async def execute(self, cmd: TranslateArticleCommand) -> Draft:
            seen.append(cmd.title)
            return _draft(slug="x")

    monkeypatch.setattr(cli_main.bootstrap, "build_translate_use_case", lambda **_: FakeUseCase())
    result = runner.invoke(cli_main.translate_queue_app, ["--config", str(empty_file)])
    assert result.exit_code == 0, result.output
    assert seen == []


def test_queue_continues_through_individual_rejections(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    queue_file = tmp_path / "queue.toml"
    queue_file.write_text(
        '[[entry]]\ntitle = "Good"\n\n[[entry]]\ntitle = "Bad"\n\n[[entry]]\ntitle = "Good2"\n',
        encoding="utf-8",
    )
    seen: list[str] = []

    class FakeUseCase:
        async def execute(self, cmd: TranslateArticleCommand) -> Draft:
            seen.append(cmd.title)
            return _draft(
                slug=cmd.title.lower(),
                passed=cmd.title.startswith("Good"),
            )

    monkeypatch.setattr(cli_main.bootstrap, "build_translate_use_case", lambda **_: FakeUseCase())
    result = runner.invoke(cli_main.translate_queue_app, ["--config", str(queue_file)])
    assert result.exit_code == 0, result.output
    assert seen == ["Good", "Bad", "Good2"]
    output_lower = result.output.lower()
    assert "good" in output_lower
    assert "bad" in output_lower
    assert "good2" in output_lower
    assert "rejected" in output_lower


def test_queue_continues_when_individual_translation_raises(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A transient error on one article must not abort the rest of the queue."""
    queue_file = tmp_path / "queue.toml"
    queue_file.write_text(
        '[[entry]]\ntitle = "First"\n\n[[entry]]\ntitle = "Boom"\n\n[[entry]]\ntitle = "Third"\n',
        encoding="utf-8",
    )
    seen: list[str] = []

    class FlakyUseCase:
        async def execute(self, cmd: TranslateArticleCommand) -> Draft:
            seen.append(cmd.title)
            if cmd.title == "Boom":
                raise RuntimeError("rpc blew up on Boom")
            return _draft(slug=cmd.title.lower())

    monkeypatch.setattr(cli_main.bootstrap, "build_translate_use_case", lambda **_: FlakyUseCase())
    result = runner.invoke(cli_main.translate_queue_app, ["--config", str(queue_file)])
    assert result.exit_code == 0, result.output
    assert seen == ["First", "Boom", "Third"]
    assert "rpc blew up on Boom" in result.output
    assert "first" in result.output.lower()
    assert "third" in result.output.lower()


def test_queue_bootstrap_failure_prints_friendly_error(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Bootstrap-time error (e.g. missing GEMINI_API_KEY) aborts the queue cleanly."""
    queue_file = tmp_path / "queue.toml"
    queue_file.write_text('[[entry]]\ntitle = "X"\n', encoding="utf-8")

    def explode(**_: object) -> object:
        raise RuntimeError("GEMINI_API_KEY is required")

    monkeypatch.setattr(cli_main.bootstrap, "build_translate_use_case", explode)
    result = runner.invoke(cli_main.translate_queue_app, ["--config", str(queue_file)])
    assert result.exit_code == 1
    assert "GEMINI_API_KEY" in result.output


def test_queue_passes_overrides_to_command(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    glossary_path = tmp_path / "g.txt"
    queue_file = tmp_path / "queue.toml"
    queue_file.write_text(
        f'[[entry]]\ntitle = "X"\nsource_lang = "ja"\nglossary = "{glossary_path}"\n',
        encoding="utf-8",
    )
    captured: list[TranslateArticleCommand] = []

    class FakeUseCase:
        async def execute(self, cmd: TranslateArticleCommand) -> Draft:
            captured.append(cmd)
            return _draft(slug="x")

    monkeypatch.setattr(cli_main.bootstrap, "build_translate_use_case", lambda **_: FakeUseCase())
    result = runner.invoke(cli_main.translate_queue_app, ["--config", str(queue_file)])
    assert result.exit_code == 0, result.output
    assert len(captured) == 1
    assert captured[0].source_lang_override == "ja"
    assert captured[0].glossary_path == str(glossary_path)
