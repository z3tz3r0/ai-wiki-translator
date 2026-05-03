"""Tests for `pick_best_source_language`."""

from __future__ import annotations

import pytest

from app.application.services.source_picker import pick_best_source_language


def test_source_picker_locale_wins() -> None:
    lang, score = pick_best_source_language(
        langlinks={"en": "Foo", "ja": "フー", "th": "ฟู"},
        claims={"P17": ["Japan"]},
        locale_to_lang={"Japan": "ja"},
    )
    assert lang == "ja"
    assert score.winning_signal == "locale"
    assert score.locale_match is True


def test_source_picker_no_locale_match_fallback_en() -> None:
    lang, score = pick_best_source_language(
        langlinks={"en": "Foo", "ja": "フー"},
        claims={"P17": ["Mars"]},
        locale_to_lang={"Japan": "ja"},
    )
    assert lang == "en"
    assert score.winning_signal == "fallback_en"
    assert score.locale_match is False


def test_source_picker_no_en_uses_first_langlink() -> None:
    lang, score = pick_best_source_language(
        langlinks={"de": "Foo", "ja": "フー"},
        claims={},
    )
    assert lang == "de"
    assert score.winning_signal == "first_langlink"
    assert score.locale_match is False


def test_source_picker_locale_mapped_lang_not_in_langlinks_falls_through() -> None:
    """When locale claim hits but the mapped lang has no langlink, fall through."""
    lang, score = pick_best_source_language(
        langlinks={"en": "Foo", "zh": "富"},  # "ja" deliberately absent
        claims={"P17": ["Japan"]},
        locale_to_lang={"Japan": "ja"},
    )
    assert lang == "en"
    assert score.winning_signal == "fallback_en"
    assert score.locale_match is False


def test_source_picker_empty_langlinks_raises() -> None:
    with pytest.raises(ValueError, match="empty"):
        pick_best_source_language(langlinks={}, claims={})


def test_source_picker_score_lang_matches_pick() -> None:
    lang, score = pick_best_source_language(
        langlinks={"en": "Foo"},
        claims={},
    )
    assert score.lang == lang


def test_source_picker_locale_match_true_when_hit() -> None:
    _, score = pick_best_source_language(
        langlinks={"th": "ฟู", "en": "Foo"},
        claims={"P17": ["Thailand"]},
        locale_to_lang={"Thailand": "th"},
    )
    assert score.locale_match is True
