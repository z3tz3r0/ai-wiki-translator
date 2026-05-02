"""Dictionary merge tests."""

from __future__ import annotations

from app.domain.merge import merge_dictionaries


def test_merge_override_wins() -> None:
    assert merge_dictionaries({"a": "1"}, {"a": "2"}) == {"a": "2"}


def test_merge_base_keys_preserved() -> None:
    assert merge_dictionaries({"a": "1", "b": "2"}, {"a": "X"}) == {"a": "X", "b": "2"}


def test_merge_empty_base() -> None:
    assert merge_dictionaries({}, {"x": "y"}) == {"x": "y"}
