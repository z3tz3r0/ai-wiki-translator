"""Tests for `wiki-refresh-rules` CLI command."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest
from typer.testing import CliRunner

from app.application.use_cases.refresh_rules import RefreshResult
from app.infrastructure.transliteration_rules import LANG_TO_TITLE
from app.interfaces.cli import main as cli_main


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


class _FakeUseCase:
    def __init__(self, results_per_call: list[list[RefreshResult]] | None = None) -> None:
        self.calls: list[list[str]] = []
        self._scripted = results_per_call or []

    async def execute(self, langs: Sequence[str]) -> list[RefreshResult]:
        self.calls.append(list(langs))
        if self._scripted:
            return self._scripted.pop(0)
        return [
            RefreshResult(lang=lang, ok=True, path=Path(f"{lang}.json"), error=None)
            for lang in langs
        ]


def test_missing_args_exits_nonzero(runner: CliRunner) -> None:
    """Guard fires before bootstrap, so no monkeypatch needed."""
    result = runner.invoke(cli_main.refresh_rules_app, [])
    assert result.exit_code != 0


def test_lang_and_all_mutually_exclusive(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        cli_main.bootstrap,
        "build_refresh_rules_use_case",
        lambda **_: _FakeUseCase(),
    )
    result = runner.invoke(cli_main.refresh_rules_app, ["--lang", "en", "--all"])
    assert result.exit_code == 2
    assert "mutually exclusive" in result.output


def test_lang_invokes_use_case_with_one_lang(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeUseCase()
    monkeypatch.setattr(
        cli_main.bootstrap,
        "build_refresh_rules_use_case",
        lambda **_: fake,
    )
    result = runner.invoke(cli_main.refresh_rules_app, ["--lang", "en"])
    assert result.exit_code == 0, result.output
    assert fake.calls == [["en"]]
    assert "ok · en" in result.output
    assert "1 ok · 0 failed" in result.output


def test_all_invokes_use_case_with_sorted_lang_to_title(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeUseCase()
    monkeypatch.setattr(
        cli_main.bootstrap,
        "build_refresh_rules_use_case",
        lambda **_: fake,
    )
    result = runner.invoke(cli_main.refresh_rules_app, ["--all"])
    assert result.exit_code == 0, result.output
    assert fake.calls == [sorted(LANG_TO_TITLE)]


def test_print_summary_includes_ok_and_fail_counts(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeUseCase(
        results_per_call=[
            [
                RefreshResult(lang="en", ok=True, path=Path("en.json"), error=None),
                RefreshResult(lang="de", ok=False, path=None, error="page layout broke"),
            ]
        ]
    )
    monkeypatch.setattr(
        cli_main.bootstrap,
        "build_refresh_rules_use_case",
        lambda **_: fake,
    )
    result = runner.invoke(cli_main.refresh_rules_app, ["--all"])
    assert result.exit_code == 0, result.output
    assert "ok · en" in result.output
    assert "FAIL · de · page layout broke" in result.output
    assert "1 ok · 1 failed" in result.output


def test_unhandled_exception_exits_1(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    def explode(**_: object) -> object:
        raise RuntimeError("boom")

    monkeypatch.setattr(cli_main.bootstrap, "build_refresh_rules_use_case", explode)
    result = runner.invoke(cli_main.refresh_rules_app, ["--lang", "en"])
    assert result.exit_code == 1
    assert "boom" in result.output
