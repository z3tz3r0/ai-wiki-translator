"""Reference-handling and block-splitting tests."""

from __future__ import annotations

from app.domain.references import (
    count_ref_markers,
    is_ref_marker,
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
    assert out == "text[[REF_1]]more"
    assert ref_map == {"[[REF_1]]": "<ref>citation</ref>"}


def test_strip_references_self_closing() -> None:
    text = "text<ref name='x' />more"
    out, ref_map = strip_references(text)
    assert out == "text[[REF_1]]more"
    assert ref_map == {"[[REF_1]]": "<ref name='x' />"}


def test_strip_then_restore_roundtrip() -> None:
    original = "para1<ref>cite1</ref> para2<ref name='y' />tail"
    stripped, ref_map = strip_references(original)
    restored = restore_references(stripped, ref_map)
    assert restored == original


def test_restore_unknown_key_passthrough() -> None:
    assert restore_references("see [[REF_99]]", {}) == "see [[REF_99]]"


def test_split_into_blocks_basic() -> None:
    wikitext = "==Header==\n[[File:foo.jpg|thumb]]\n\nParagraph text.\n"
    blocks = split_into_blocks(wikitext)
    assert "==Header==" in blocks
    assert any("Paragraph text." in b for b in blocks)
    assert all(b.strip() for b in blocks)


def test_strip_references_sequential_numbering() -> None:
    """Multiple refs receive incrementing [[REF_1]], [[REF_2]] markers in source order."""
    text = "a<ref>first</ref>b<ref name='x' />c"
    out, ref_map = strip_references(text)
    assert out == "a[[REF_1]]b[[REF_2]]c"
    assert ref_map == {
        "[[REF_1]]": "<ref>first</ref>",
        "[[REF_2]]": "<ref name='x' />",
    }


def test_strip_references_nested_tags() -> None:
    """Regression: _REF_TAG_RE must not stop at the first `<` inside the body.

    Legacy `[^<]*` would truncate at the inner `<cite>` tag and mis-pair the
    outer `</ref>`. The fix uses `.*?` with re.DOTALL.
    """
    text = "text<ref><cite>Author, 2024</cite></ref>tail"
    out, ref_map = strip_references(text)
    assert out == "text[[REF_1]]tail"
    assert ref_map == {"[[REF_1]]": "<ref><cite>Author, 2024</cite></ref>"}


def test_restore_tolerates_spacing_variants_of_the_marker() -> None:
    """LLMs sometimes pad or respace the marker · it must still map back."""
    ref_map = {"[[REF_1]]": "<ref>a</ref>", "[[REF_2]]": "<ref>b</ref>"}
    assert restore_references("x[[ REF_1 ]] y[[REF 2]]", ref_map) == "x<ref>a</ref> y<ref>b</ref>"


def test_restore_leaves_literal_bracketed_numbers_alone() -> None:
    """Regression: the old `[N]` placeholder turned a literal "[12]" into a reference."""
    ref_map = {"[[REF_12]]": "<ref>a</ref>"}
    assert restore_references("see note [12] here", ref_map) == "see note [12] here"


def test_count_ref_markers_finds_unrestored_markers() -> None:
    assert count_ref_markers("a[[REF_3]] b [[ REF_4 ]] c [12]") == 2


def test_is_ref_marker_matches_link_targets_that_are_markers() -> None:
    assert is_ref_marker("REF_55")
    assert is_ref_marker(" REF 7 ")
    assert not is_ref_marker("Reference manager")
