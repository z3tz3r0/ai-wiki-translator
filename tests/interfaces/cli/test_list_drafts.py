"""Tests for `wiki-list-drafts` CLI command."""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from app.application.dto import DraftMetadata
from app.interfaces.cli import main as cli_main


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_list_drafts_empty_prints_placeholder(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeUseCase:
        async def execute(self, since: datetime.datetime | None = None) -> list[DraftMetadata]:
            return []

    monkeypatch.setattr(cli_main.bootstrap, "build_list_drafts_use_case", lambda **_: FakeUseCase())
    result = runner.invoke(cli_main.list_drafts_app, [])
    assert result.exit_code == 0, result.output
    assert "no drafts" in result.output.lower()


def test_list_drafts_prints_each_draft(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    drafts = [
        DraftMetadata(
            slug="newer", when=datetime.date(2026, 5, 3), dir=tmp_path / "2026-05-03" / "newer"
        ),
        DraftMetadata(
            slug="older", when=datetime.date(2026, 5, 1), dir=tmp_path / "2026-05-01" / "older"
        ),
    ]

    class FakeUseCase:
        async def execute(self, since: datetime.datetime | None = None) -> list[DraftMetadata]:
            return drafts

    monkeypatch.setattr(cli_main.bootstrap, "build_list_drafts_use_case", lambda **_: FakeUseCase())
    result = runner.invoke(cli_main.list_drafts_app, [])
    assert result.exit_code == 0, result.output
    assert "2026-05-03" in result.output
    assert "newer" in result.output
    assert "2026-05-01" in result.output
    assert "older" in result.output


def test_list_drafts_since_filter_passed_to_use_case(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, datetime.datetime | None] = {}

    class FakeUseCase:
        async def execute(self, since: datetime.datetime | None = None) -> list[DraftMetadata]:
            captured["since"] = since
            return []

    monkeypatch.setattr(cli_main.bootstrap, "build_list_drafts_use_case", lambda **_: FakeUseCase())
    result = runner.invoke(cli_main.list_drafts_app, ["--since", "2026-05-02"])
    assert result.exit_code == 0, result.output
    assert captured["since"] == datetime.datetime(2026, 5, 2)


def test_list_drafts_no_since_passes_none(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, datetime.datetime | None] = {}

    class FakeUseCase:
        async def execute(self, since: datetime.datetime | None = None) -> list[DraftMetadata]:
            captured["since"] = since
            return []

    monkeypatch.setattr(cli_main.bootstrap, "build_list_drafts_use_case", lambda **_: FakeUseCase())
    result = runner.invoke(cli_main.list_drafts_app, [])
    assert result.exit_code == 0, result.output
    assert captured["since"] is None


def test_list_drafts_invalid_since_format_exits_nonzero(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Non-ISO `--since` value must fail fast and not invoke the use case."""

    class FakeUseCase:
        async def execute(self, since: datetime.datetime | None = None) -> list[DraftMetadata]:
            pytest.fail("use case should not run when --since is invalid")

    monkeypatch.setattr(cli_main.bootstrap, "build_list_drafts_use_case", lambda **_: FakeUseCase())
    result = runner.invoke(cli_main.list_drafts_app, ["--since", "not-a-date"])
    assert result.exit_code != 0
    assert "since" in result.output.lower() or "yyyy-mm-dd" in result.output.lower()


def test_list_drafts_use_case_failure_prints_friendly_error(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An exception from the storage adapter surfaces as a one-line error, exit 1."""

    class BoomUseCase:
        async def execute(self, since: datetime.datetime | None = None) -> list[DraftMetadata]:
            raise RuntimeError("disk is on fire")

    monkeypatch.setattr(cli_main.bootstrap, "build_list_drafts_use_case", lambda **_: BoomUseCase())
    result = runner.invoke(cli_main.list_drafts_app, [])
    assert result.exit_code == 1
    assert "disk is on fire" in result.output


def test_list_drafts_routes_output_dir_to_bootstrap(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured_kwargs: dict[str, Path] = {}

    class FakeUseCase:
        async def execute(self, since: datetime.datetime | None = None) -> list[DraftMetadata]:
            return []

    def fake_build(**kwargs: Path) -> FakeUseCase:
        captured_kwargs.update(kwargs)
        return FakeUseCase()

    monkeypatch.setattr(cli_main.bootstrap, "build_list_drafts_use_case", fake_build)
    result = runner.invoke(cli_main.list_drafts_app, ["--output-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert captured_kwargs["output_dir"] == tmp_path
