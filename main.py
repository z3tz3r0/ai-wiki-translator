import asyncio
import aiofiles
import re
from dataclasses import dataclass
from typing import List, Dict

from utils import load_glossary, read_file, remove_comments, replace_references, replace_image_des, replace_quote, replace_bullet_point, replace_with_dictionary
from translator import translate_links, translate_text
from assistant import GenAI
from wikipedia import Wikipedia

TITLE_NAME = "Narcissism"
TH_TITLE_NAME = "ความหลงตนเอง"
GLOSSARY_FILE = "my_glossary.txt"
SYS_PROMPT = "system_instructionFULL.md"

@dataclass
class WikiSection:
    """Represents a section of the Wikipedia wikitext."""
    task_id: int
    content: str
    type: str
    mode: str # "ASYNC" or "FIFO"

class WikiTranslator:
    """Translates a Wikipedia page from English to Thai."""
    def __init__(self, title_name: str, th_title_name: str, glossary_file: str) -> None:
        print("Creating WikiTranslator object")
        self.glossary: Dict[str, str] = load_glossary(glossary_file)
        self.page = Wikipedia(title_name)
        self.wikitext_raw: str = remove_comments(self.page.wikitext_no_ref)
        self.wikitext: List[str] = self.preprocess_wikitext(Wikipedia.convert_to_list(self.wikitext_raw))
        self.all_ref_tag: Dict[str, str] = self.page.ref_map
        self.dictionary: Dict[str, str] = translate_links(self.page.no_th_titles, self.page.dictonary)
        self.system_instruction: str = read_file(file_path=SYS_PROMPT).format(
            title_name=title_name, th_title_name=th_title_name, dictionary=self.dictionary
        )
        self.assistant = GenAI(self.system_instruction)

    def preprocess_wikitext(self, wikitext_list: List[str]) -> List[WikiSection]:
        """
        Preprocesses the wikitext list into a list of WikiSection objects.

        Args:
            wikitext_list: A list of strings representing lines of wikitext.

        Returns:
            A list of WikiSection objects.
        """
        print("Preprocessing wikitext")
        processed: List[WikiSection] = []
        for id, item in enumerate(wikitext_list):
            section_type = self._determine_section_type(item)
            mode = "ASYNC" if section_type != "text" else "FIFO"
            processed.append(WikiSection(task_id=id + 1, content=item, type=section_type, mode=mode))
        return processed

    def _determine_section_type(self, item: str) -> str:
        """Determines the type of a wikitext item."""
        if item in self.glossary:
            return "glossary"
        elif not item:
            return "empty"
        elif self._is_section_header(item):
            return "section_header"
        elif self._is_image(item):
            return "image"
        elif self._is_quote(item):
            return "quote"
        elif self._is_bullet_point(item):
            return "bullet_point"
        elif self._is_category(item):
            return "category"
        elif self._is_template(item):
            return "template"
        else:
            return "text"

    def _is_section_header(self, item: str) -> bool:
        """Checks if an item is a section header."""
        return item.startswith("==") and item.endswith("==")

    def _is_image(self, item: str) -> bool:
        """Checks if an item is an image tag."""
        return re.match(r"\[{2}File:.*?\|*[^\]]*\]{2}(?=\n)", item) is not None

    def _is_quote(self, item: str) -> bool:
        """Checks if an item is a quote template."""
        return re.match(r"\{\{(?:blockquote|quote)\|.*\}\}", item, flags=re.DOTALL) is not None

    def _is_template(self, item: str) -> bool:
        """Checks if an item is a template or internal link (excluding files)."""
        return (item.startswith("{{") and item.endswith("}}")) or \
               (item.startswith("[[") and item.endswith("]]"))

    def _is_bullet_point(self, item: str) -> bool:
        """Checks if an item is a bullet point."""
        return re.match(r"^[•\*]{1,}\s*(?:\[{1,2}|\{*).*(?:\]{1,2}|\}*)", item, flags=re.MULTILINE) is not None

    def _is_category(self, item: str) -> bool:
        """Checks if an item is a category link."""
        return re.match(r"\[\[[Cc]ategory:.*\]\]", item, flags=re.MULTILINE) is not None

    async def processing(self, section: WikiSection) -> str:
        """Processes a single WikiSection based on its type."""
        print(f"  section {section.task_id} type: {section.type}")
        if section.type == "glossary":
            print(f"    Using glossary for: {section.content}")
            return self.glossary.get(section.content, "") # Return empty string if not found
        elif section.type == "empty":
            print(f"    Empty section: {section.content}")
            return ""
        elif section.type == "section_header":
            print(f"    Translating section header: {section.content}")
            return translate_text(section.content)
        elif section.type == "image":
            print(f"    Replacing image description: {section.content}")
            return replace_image_des(section.content, self.dictionary)
        elif section.type == "quote":
            print(f"    Translating blockquote: {section.content}")
            return replace_quote(section.content, self.dictionary)
        elif section.type == "bullet_point":
            print(f"    Keeping bullet point: {section.content}")
            return replace_bullet_point(section.content, self.dictionary)
        elif section.type == "category":
            print(f"    Replacing with dictionary: {section.content}")
            return replace_with_dictionary(section.content, self.dictionary)
        elif section.type == "template":
            print(f"    Keeping template: {section.content}")
            return section.content
        else: # type == "text"
            print(f"    Sending to assistant: {section.content}")
            await asyncio.sleep(6) # Add a delay to avoid hitting API limits
            response = self.assistant.send_msg(section.content)
            print(f"    Translated to: {response.text}")
            return response.text

    async def process_tasks(self, wikitext_list: List[WikiSection]) -> List[str]:
        """
        Processes a list of WikiSection objects, handling ASYNC and FIFO modes.

        Args:
            wikitext_list: A list of WikiSection objects.

        Returns:
            A list of translated strings in the original order.
        """
        print("Starting task processing".center(50, "="))
        async_tasks = {item.task_id: self.processing(item) for item in wikitext_list if item.mode == 'ASYNC'}
        fifo_tasks = {item.task_id: self.processing(item) for item in wikitext_list if item.mode == 'FIFO'}

        # Process FIFO tasks sequentially
        fifo_results = {}
        for task_id, task in fifo_tasks.items():
            fifo_results[task_id] = await task

        # Process ASYNC tasks concurrently
        async_results = await asyncio.gather(*async_tasks.values())
        async_results_dict = dict(zip(async_tasks.keys(), async_results))

        # Combine results in original order
        final_results = []
        for item in wikitext_list:
            if item.mode == 'ASYNC':
                final_results.append(async_results_dict[item.task_id])
            elif item.mode == 'FIFO':
                final_results.append(fifo_results[item.task_id])

        print("Task processing completed".center(50, "="))
        return final_results

async def main():
    """Main function to run the WikiTranslator."""
    translator = WikiTranslator(
        title_name=TITLE_NAME, th_title_name=TH_TITLE_NAME, glossary_file=GLOSSARY_FILE
    )

    translated_sections = await translator.process_tasks(translator.wikitext)

    async with aiofiles.open("output.txt", "w", encoding="utf-8") as f:
        final_translation = "\n".join(translated_sections)
        final_translation = replace_references(final_translation, translator.all_ref_tag)
        await f.write(final_translation)

if __name__ == "__main__":
    asyncio.run(main())
