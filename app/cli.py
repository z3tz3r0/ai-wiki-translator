"""Command-line interface for translating Wikipedia articles."""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from app.models.translation_request import TranslationRequest
from app.services.wiki_translation_service import WikiTranslationService


load_dotenv()

DEFAULT_PROMPT_PATH = os.environ.get(
    "PROMPT_TEMPLATE_PATH", "app/prompts/system_instruction_en.md"
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Translate Wikipedia articles into Thai")
    parser.add_argument("title", help="English Wikipedia article title")
    parser.add_argument("thai_title", help="Desired Thai article title")
    parser.add_argument(
        "--glossary",
        help="Path to a glossary file (defaults to my_glossary.txt)",
    )
    parser.add_argument(
        "--prompt",
        help="Path to a system prompt template",
    )
    parser.add_argument(
        "--output",
        default="output.txt",
        help="File to write the translated article to",
    )
    return parser


def run_cli(
    *,
    title: str,
    thai_title: str,
    glossary: Optional[str],
    prompt: Optional[str],
    output: str,
) -> str:
    prompt_path = prompt or DEFAULT_PROMPT_PATH
    service = WikiTranslationService(prompt_template=prompt_path)

    request = TranslationRequest(
        title_name=title,
        thai_title_name=thai_title,
        glossary_path=glossary,
    )
    translation = asyncio.run(service.translate(request))

    output_path = Path(output)
    output_path.write_text(translation, encoding="utf-8")
    return str(output_path)


def main() -> None:
    parser = build_argument_parser()
    args = parser.parse_args()
    output_path = run_cli(
        title=args.title,
        thai_title=args.thai_title,
        glossary=args.glossary,
        prompt=args.prompt,
        output=args.output,
    )
    print(f"Translation saved to {output_path}")


if __name__ == "__main__":
    main()

