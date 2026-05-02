"""Section classification tests."""

from __future__ import annotations

from app.domain.classification import classify_section, execution_mode_for
from app.domain.values import ExecutionMode, SectionType


def test_empty_string() -> None:
    assert classify_section("", {}) is SectionType.EMPTY


def test_glossary_hit() -> None:
    glossary = {"Narcissism": "ความหลงตนเอง"}
    assert classify_section("Narcissism", glossary) is SectionType.GLOSSARY


def test_section_header() -> None:
    assert classify_section("==History==", {}) is SectionType.SECTION_HEADER


def test_image_block() -> None:
    block = "[[File:Example.jpg|thumb|Caption]]\n"
    assert classify_section(block, {}) is SectionType.IMAGE


def test_image_no_trailing_newline() -> None:
    """Regression for legacy bug 3: lookahead `(?=\\n)` rejected last-line images."""
    block = "[[File:Example.jpg|thumb|Caption]]"
    assert classify_section(block, {}) is SectionType.IMAGE


def test_quote_block() -> None:
    assert classify_section("{{blockquote|some text}}", {}) is SectionType.QUOTE


def test_bullet_asterisk() -> None:
    assert classify_section("* [[link]]", {}) is SectionType.BULLET_POINT


def test_category_lowercase_c() -> None:
    assert classify_section("[[category:Foo]]", {}) is SectionType.CATEGORY


def test_template_double_brace() -> None:
    assert classify_section("{{Infobox person|name=x}}", {}) is SectionType.TEMPLATE


def test_plain_text_falls_through() -> None:
    assert classify_section("This is a paragraph.", {}) is SectionType.TEXT


def test_execution_mode_text_is_fifo() -> None:
    assert execution_mode_for(SectionType.TEXT) is ExecutionMode.FIFO


def test_execution_mode_non_text_is_async() -> None:
    assert execution_mode_for(SectionType.IMAGE) is ExecutionMode.ASYNC
    assert execution_mode_for(SectionType.QUOTE) is ExecutionMode.ASYNC
    assert execution_mode_for(SectionType.GLOSSARY) is ExecutionMode.ASYNC
    assert execution_mode_for(SectionType.EMPTY) is ExecutionMode.ASYNC
    assert execution_mode_for(SectionType.SECTION_HEADER) is ExecutionMode.ASYNC
    assert execution_mode_for(SectionType.BULLET_POINT) is ExecutionMode.ASYNC
    assert execution_mode_for(SectionType.CATEGORY) is ExecutionMode.ASYNC
    assert execution_mode_for(SectionType.TEMPLATE) is ExecutionMode.ASYNC
