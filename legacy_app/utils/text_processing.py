"""Utility helpers for glossary loading and wikitext manipulation."""

from __future__ import annotations

import os
import re
from typing import Callable, Dict


def load_glossary(file_path: str) -> Dict[str, str]:
    """Load a glossary file in "term:translation" format."""

    abs_path = os.path.abspath(file_path)
    base_dir = os.path.abspath(os.getcwd())
    if not abs_path.startswith(base_dir):
        raise ValueError("Access denied: glossary path must be inside the project directory")
    if not os.path.isfile(abs_path):
        raise ValueError(f"Glossary file not found: {file_path}")

    glossary: Dict[str, str] = {}
    with open(abs_path, "r", encoding="utf-8") as handle:
        for line in handle:
            if ":" not in line:
                continue
            term, translation = line.strip().split(":", 1)
            glossary[term.strip()] = translation.strip()
    return glossary


def replace_with_dictionary(
    text: str,
    dictionary: Dict[str, str],
    translate: Callable[[str], str],
) -> str:
    pattern = r"\[\[(?!File:)(?:([^#|\]]+)(?:#[^|\]]*)?(?:\|([^\]]+))?)\]\]"
    replaced = text
    for original_link, display in re.findall(pattern, text):
        display_text = display or original_link
        if display_text != original_link:
            translated_display = translate(display_text)
            replaced = replaced.replace(display_text, translated_display)
        replacement = dictionary.get(original_link)
        if replacement:
            replaced = replaced.replace(original_link, replacement)
        else:
            translated_original = translate(original_link)
            replaced = replaced.replace(original_link, translated_original)
    return replaced


def replace_image_description(
    text: str,
    dictionary: Dict[str, str],
    translate: Callable[[str], str],
) -> str:
    pattern = r"\[{2}File:.*?(?:\|.*\|)(.*|\n*?|[^\]]*)\]{2}(?=\n)"
    match = re.search(pattern, text)
    if not match:
        return text
    description = match.group(1)
    translated_description = translate(
        replace_with_dictionary(description, dictionary, translate)
    )
    return text.replace(description, translated_description).replace("File:", "ไฟล์:")


def replace_quote(
    text: str,
    dictionary: Dict[str, str],
    translate: Callable[[str], str],
) -> str:
    pattern = r"\{\{(?:blockquote|quote)\|(.*)\}\}"
    match = re.search(pattern, text, flags=re.DOTALL)
    if not match:
        return text
    quote_content = match.group(1)
    translated = translate(replace_with_dictionary(quote_content, dictionary, translate))
    return text.replace(quote_content, translated)


def replace_bullet_point(
    text: str,
    dictionary: Dict[str, str],
    translate: Callable[[str], str],
) -> str:
    pattern = r"^[•\*]+\s*(.*)"
    match = re.search(pattern, text)
    if not match:
        return text
    bullet_content = match.group(1)
    translated = translate(replace_with_dictionary(bullet_content, dictionary, translate))
    return text.replace(bullet_content, translated)


def read_file(file_path: str) -> str:
    abs_path = os.path.abspath(file_path)
    base_dir = os.path.abspath(os.getcwd())
    if not abs_path.startswith(base_dir):
        raise ValueError("Access denied: file path must be inside the project directory")
    if not os.path.isfile(abs_path):
        raise ValueError(f"File not found: {file_path}")
    with open(abs_path, "r", encoding="utf-8") as handle:
        return handle.read()


def remove_comments(text: str) -> str:
    pattern = r"<!--[^\>]*>"
    return re.sub(pattern, "", text, flags=re.DOTALL)
