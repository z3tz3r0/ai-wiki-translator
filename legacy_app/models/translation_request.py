"""Data structures for translation tasks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class TranslationRequest:
    title_name: str
    thai_title_name: str
    glossary_path: Optional[str] = None
