"""End-to-end smoke against the live Wikipedia + Wikidata + Gemini + Translate stack.

Skipped on CI and when credentials are missing. Run locally with::

    GEMINI_API_KEY=... GOOGLE_CLOUD_PROJECT=... uv run pytest -m integration \\
        tests/interfaces/cli/test_integration.py
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from app.interfaces.cli import main as cli_main

_BENCHMARK_TITLE = "ป๋วย อึ๊งภากรณ์"


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("GEMINI_API_KEY") is None
    or os.environ.get("GOOGLE_CLOUD_PROJECT") is None
    or os.environ.get("CI") is not None,
    reason="set GEMINI_API_KEY + GOOGLE_CLOUD_PROJECT and run outside CI",
)
def test_translate_benchmark_writes_paste_ready_draft(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli_main.translate_app,
        [_BENCHMARK_TITLE, "--output-dir", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output

    date_dirs = [p for p in tmp_path.iterdir() if p.is_dir()]
    assert len(date_dirs) == 1, f"expected one date dir, got {date_dirs}"
    slug_dirs = [p for p in date_dirs[0].iterdir() if p.is_dir()]
    assert len(slug_dirs) == 1, f"expected one slug dir, got {slug_dirs}"

    slug_dir = slug_dirs[0]
    wikitext_files = list(slug_dir.glob("*.wikitext"))
    review_files = list(slug_dir.glob("*.review.md"))
    assert wikitext_files, f"no .wikitext under {slug_dir}"
    assert review_files, f"no .review.md under {slug_dir}"
    assert wikitext_files[0].read_text(encoding="utf-8")
    assert review_files[0].read_text(encoding="utf-8")
