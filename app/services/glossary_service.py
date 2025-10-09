"""Glossary loading utilities."""

from __future__ import annotations

from typing import Dict, Optional

from app.utils.text_processing import load_glossary


class GlossaryService:
    """Loads glossary files with optional defaults."""

    def __init__(self, default_path: str = "my_glossary.txt") -> None:
        self.default_path = default_path

    def load(self, path: Optional[str] = None) -> Dict[str, str]:
        target = path or self.default_path
        return load_glossary(target)

