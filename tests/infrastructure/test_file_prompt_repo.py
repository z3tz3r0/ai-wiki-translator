"""Tests for `FilePromptRepository`."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.application.ports import PromptTemplateRepository
from app.infrastructure.file_prompt_repo import FilePromptRepository


def test_satisfies_prompt_repo_protocol(tmp_path: Path) -> None:
    repo = FilePromptRepository(prompts_dir=tmp_path)
    assert isinstance(repo, PromptTemplateRepository)


async def test_load_returns_template_content(tmp_path: Path) -> None:
    (tmp_path / "system_instruction_th.md").write_text("You are a translator.", encoding="utf-8")
    repo = FilePromptRepository(prompts_dir=tmp_path)
    body = await repo.load("system_instruction_th")
    assert body == "You are a translator."


async def test_load_unknown_template_raises_file_not_found(tmp_path: Path) -> None:
    repo = FilePromptRepository(prompts_dir=tmp_path)
    with pytest.raises(FileNotFoundError):
        await repo.load("missing")


@pytest.mark.parametrize(
    "evil",
    [
        "../etc/passwd",
        "foo/bar",
        "..",
        ".",
        "abs/../escape",
        "",
        "/abs/path",
        "foo\nbar",  # newline control char
        "foo\x00bar",  # null byte
    ],
)
async def test_load_rejects_path_traversal_template_id(tmp_path: Path, evil: str) -> None:
    repo = FilePromptRepository(prompts_dir=tmp_path)
    with pytest.raises(ValueError, match="template_id"):
        await repo.load(evil)


async def test_load_handles_utf8_thai_content(tmp_path: Path) -> None:
    (tmp_path / "th_prompt.md").write_text("คุณเป็นนักแปล", encoding="utf-8")
    repo = FilePromptRepository(prompts_dir=tmp_path)
    assert await repo.load("th_prompt") == "คุณเป็นนักแปล"
