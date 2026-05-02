"""Represents a fragment of wikitext that needs processing."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WikiSection:
    task_id: int
    content: str
    type: str
    mode: str  # "ASYNC" or "FIFO"
