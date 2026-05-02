"""Google Cloud Translation service wrapper."""

from __future__ import annotations

import os
from typing import Iterable, List, Sequence

from google.cloud import translate_v3


class GoogleTranslationService:
    """A thin wrapper around the Google Cloud Translation API."""

    def __init__(self, project_id: str | None = None) -> None:
        project = project_id or os.environ.get("GOOGLE_CLOUD_PROJECT_ID")
        if not project:
            raise ValueError(
                "GOOGLE_CLOUD_PROJECT_ID environment variable is not set; "
                "cannot initialise GoogleTranslationService"
            )
        self.parent = f"projects/{project}"
        self.client = translate_v3.TranslationServiceClient()

    def translate_text(
        self,
        text_or_texts: str | Sequence[str],
        *,
        target_language: str = "th",
        source_language: str = "en",
    ) -> str | List[str]:
        contents = [text_or_texts] if isinstance(text_or_texts, str) else list(text_or_texts)
        request = translate_v3.TranslateTextRequest(
            contents=contents,
            target_language_code=target_language,
            source_language_code=source_language,
            parent=self.parent,
        )
        response = self.client.translate_text(request=request)
        translations = [translation.translated_text for translation in response.translations]
        return translations[0] if isinstance(text_or_texts, str) else translations

    def enrich_title_dictionary(
        self,
        source_titles: Iterable[str],
        existing_mapping: dict[str, str],
        *,
        target_language: str = "th",
        source_language: str = "en",
    ) -> dict[str, str]:
        titles = list(source_titles)
        if not titles:
            return dict(existing_mapping)

        translated_titles = self.translate_text(
            titles,
            target_language=target_language,
            source_language=source_language,
        )
        enriched = dict(zip(titles, translated_titles))
        enriched.update(existing_mapping)
        return enriched
