"""Wikitext transformation + glossary parsing tests."""

from __future__ import annotations

from app.domain.text_transforms import (
    parse_glossary_lines,
    replace_bullet_point,
    replace_image_description,
    replace_quote,
    replace_with_dictionary,
)


def _identity(text: str) -> str:
    return text


def test_parse_glossary_lines_basic() -> None:
    assert parse_glossary_lines(["foo:bar", "baz:qux"]) == {"foo": "bar", "baz": "qux"}


def test_parse_glossary_lines_skip_no_colon() -> None:
    assert parse_glossary_lines(["no colon line", "a:b"]) == {"a": "b"}


def test_replace_with_dictionary_known_link() -> None:
    out = replace_with_dictionary("[[Python]]", {"Python": "ไพธอน"}, _identity)
    assert out == "[[ไพธอน]]"


def test_replace_image_description() -> None:
    out = replace_image_description("[[File:X.jpg|thumb|A dog]]\n", {}, _identity)
    assert "ไฟล์:" in out


def test_replace_quote_content() -> None:
    out = replace_quote("{{quote|Hello world}}", {}, str.upper)
    assert out == "{{quote|HELLO WORLD}}"


def test_replace_bullet_point() -> None:
    out = replace_bullet_point("* Some text", {}, str.upper)
    assert out == "* SOME TEXT"


def test_replace_with_dictionary_pipe_display_translates_display() -> None:
    out = replace_with_dictionary("[[Python|Pythonic]]", {"Python": "ไพธอน"}, str.upper)
    assert out == "[[ไพธอน|PYTHONIC]]"


def test_replace_with_dictionary_link_not_in_dictionary_uses_translator() -> None:
    out = replace_with_dictionary("[[Foo]]", {}, str.upper)
    assert out == "[[FOO]]"


def test_replace_image_description_no_match_passthrough() -> None:
    assert replace_image_description("nothing here", {}, _identity) == "nothing here"


def test_replace_quote_no_match_passthrough() -> None:
    assert replace_quote("nothing here", {}, _identity) == "nothing here"


def test_replace_bullet_point_no_match_passthrough() -> None:
    assert replace_bullet_point("nothing here", {}, _identity) == "nothing here"


def test_replace_with_dictionary_prefix_collision() -> None:
    """Regression for legacy bug: `str.replace` corrupted prefix-overlapping links."""
    out = replace_with_dictionary(
        "[[Alpha]] [[AlphaGo]]",
        {"Alpha": "X", "AlphaGo": "Y"},
        str.upper,
    )
    assert out == "[[X]] [[Y]]"


def test_replace_with_dictionary_pipe_display_equals_link() -> None:
    """When display duplicates the link, both sides translate together."""
    out = replace_with_dictionary("[[Python|Python]]", {"Python": "ไพธอน"}, str.upper)
    assert out == "[[ไพธอน|ไพธอน]]"
