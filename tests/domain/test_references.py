"""Reference-handling and block-splitting tests."""

from __future__ import annotations

from app.domain.references import (
    remove_comments,
    restore_references,
    split_into_blocks,
    strip_references,
)


def test_remove_comments_basic() -> None:
    assert remove_comments("text <!-- comment --> end") == "text  end"


def test_remove_comments_with_gt_inside() -> None:
    """Regression for legacy bug: pattern closing on first `>` inside a comment."""
    assert remove_comments("<!-- a > b -->") == ""


def test_remove_comments_multiline() -> None:
    assert remove_comments("<!--\nmulti\nline\n-->") == ""


def test_strip_references_numbered() -> None:
    text = "text<ref>citation</ref>more"
    out, ref_map = strip_references(text)
    assert out == "text[1]more"
    assert ref_map == {"[1]": "<ref>citation</ref>"}


def test_strip_references_self_closing() -> None:
    text = "text<ref name='x' />more"
    out, ref_map = strip_references(text)
    assert out == "text[1]more"
    assert ref_map == {"[1]": "<ref name='x' />"}


def test_strip_then_restore_roundtrip() -> None:
    original = "para1<ref>cite1</ref> para2<ref name='y' />tail"
    stripped, ref_map = strip_references(original)
    restored = restore_references(stripped, ref_map)
    assert restored == original


def test_restore_unknown_key_passthrough() -> None:
    assert restore_references("see [99]", {}) == "see [99]"


def test_split_into_blocks_basic() -> None:
    wikitext = "==Header==\n[[File:foo.jpg|thumb]]\n\nParagraph text.\n"
    blocks = split_into_blocks(wikitext)
    assert "==Header==" in blocks
    assert any("Paragraph text." in b for b in blocks)
    assert all(b.strip() for b in blocks)


def test_strip_references_sequential() -> None:
    """Verify that multiple refs receive incrementing [1], [2] placeholders."""
    text = "a<ref>first</ref>b<ref name='x' />c"
    out, ref_map = strip_references(text)
    assert out == "a[1]b[2]c"
    assert ref_map == {
        "[1]": "<ref>first</ref>",
        "[2]": "<ref name='x' />",
    }
