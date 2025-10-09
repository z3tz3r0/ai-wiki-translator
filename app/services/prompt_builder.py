"""Prompt templating utilities."""

from __future__ import annotations

import json
from typing import Dict

from app.utils.text_processing import read_file


class PromptBuilder:
    """Formats the system instruction used by the assistant."""

    def __init__(self, template_path: str) -> None:
        self.template_path = template_path

    def build(self, title_name: str, th_title_name: str, dictionary: Dict[str, str]) -> str:
        template = read_file(self.template_path)
        dictionary_json = json.dumps(dictionary, ensure_ascii=False, indent=2)
        return template.format(
            title_name=title_name,
            th_title_name=th_title_name,
            dictionary=dictionary_json,
        )

