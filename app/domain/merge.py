"""Pure dictionary merge: override wins over base."""

from __future__ import annotations

from app.domain.values import Dictionary


def merge_dictionaries(base: Dictionary, override: Dictionary) -> Dictionary:
    """Return a new dict with `override` keys winning over `base`.

    Mirrors legacy `enrich_title_dictionary` precedence: machine-translated
    fallbacks become the base, Wikipedia-derived langlinks override them.
    """
    return {**base, **override}
