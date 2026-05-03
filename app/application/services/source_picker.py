"""Pure-function source-language picker · locale + langlinks → winning lang."""

from __future__ import annotations

from app.application.dto import SourceScore


def pick_best_source_language(
    langlinks: dict[str, str],
    claims: dict[str, list[str]],
    country_claim_id: str = "P17",
    locale_to_lang: dict[str, str] | None = None,
) -> tuple[str, SourceScore]:
    """Pick the language to translate FROM, given langlinks + Wikidata claims.

    Order of preference:
      1. **Locale heuristic**: if any value of the country/locale claim
         (default `P17`) maps via `locale_to_lang` to a key present in
         `langlinks`, that lang wins (`winning_signal="locale"`).
      2. **English fallback**: `"en"` in `langlinks` → wins
         (`winning_signal="fallback_en"`).
      3. **First langlink**: ordered-dict insertion order, marked
         `winning_signal="first_langlink"`. Phase 3 may override this
         choice using real word-count comparisons before the use case
         finalizes the source pick.

    Empty `langlinks` raises `ValueError` · the caller has nothing to translate.

    Word/ref counts in the returned `SourceScore` are placeholder zeros at
    Phase 2; Phase 3 will pass them in after fetching candidate articles.
    """
    if not langlinks:
        raise ValueError("langlinks is empty · no source language to pick")

    if locale_to_lang:
        for value in claims.get(country_claim_id, []):
            mapped = locale_to_lang.get(value)
            if mapped and mapped in langlinks:
                return mapped, SourceScore(
                    lang=mapped,
                    word_count=0,
                    ref_count=0,
                    locale_match=True,
                    winning_signal="locale",
                )

    if "en" in langlinks:
        return "en", SourceScore(
            lang="en",
            word_count=0,
            ref_count=0,
            locale_match=False,
            winning_signal="fallback_en",
        )

    first = next(iter(langlinks))
    return first, SourceScore(
        lang=first,
        word_count=0,
        ref_count=0,
        locale_match=False,
        winning_signal="first_langlink",
    )
