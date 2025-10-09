"""Generative AI assistant integration."""

from __future__ import annotations

import os
from typing import Optional

import google.generativeai as genai


class GenerativeAssistantService:
    """Wrapper for Google Generative AI chat completions."""

    def __init__(
        self,
        system_instruction: str,
        *,
        api_key: Optional[str] = None,
        model_name: str = "gemini-1.5-flash",
    ) -> None:
        key = api_key or os.environ.get("GOOGLE_GENAI_API_KEY") or os.environ.get("API_KEY")
        if not key:
            raise ValueError("GOOGLE_GENAI_API_KEY environment variable is required")
        genai.configure(api_key=key)
        self.model = genai.GenerativeModel(
            model_name=model_name,
            generation_config={
                "temperature": 1,
                "top_p": 0.95,
                "top_k": 64,
                "max_output_tokens": 8192,
                "response_mime_type": "text/plain",
            },
            safety_settings="BLOCK_NONE",
            system_instruction=system_instruction,
        )
        self.chat = self.model.start_chat(history=[])

    def send_message(self, message: str) -> str:
        response = self.chat.send_message(content=message)
        return response.text

