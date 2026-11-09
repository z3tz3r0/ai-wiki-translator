"""Load skill scripts (they live under .claude/skills, outside any package) as modules."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

SKILLS = Path(__file__).resolve().parents[2] / ".claude" / "skills"


def _load(relative: str) -> ModuleType:
    path = SKILLS / relative
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = module  # dataclasses resolve annotations through sys.modules
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def outline() -> ModuleType:
    return _load("thwiki-translate/scripts/outline.py")


@pytest.fixture(scope="session")
def checker() -> ModuleType:
    return _load("thwiki-review/scripts/check_wikitext.py")
