import re
from translator import translate_text

import os
from pathlib import Path

def load_glossary(file_path: str) -> dict[str, str]:
    """
    Loads a glossary from a file.

    Args:
        file_path: The path to the glossary file.

    Returns:
        A dictionary mapping English terms to Thai translations.
    
    Raises:
        ValueError: If the file path is invalid or attempts path traversal.
    """
    # Validate and sanitize the file path to prevent path traversal
    try:
        # Convert to absolute path and check if it's within the current directory
        abs_path = os.path.abspath(file_path)
        base_dir = os.path.abspath(os.getcwd())
        
        if not abs_path.startswith(base_dir):
            raise ValueError(f"Access denied: File path must be within the application directory")
        
        # Ensure the file exists
        if not os.path.isfile(abs_path):
            raise ValueError(f"Glossary file not found: {file_path}")
            
        print(f"Loading glossary from {abs_path}")
        glossary = {}
        with open(abs_path, 'r', encoding='utf-8') as f:
            for line in f:
                if ":" in line:
                    en_term, th_translation = line.strip().split(":", 1)
                    glossary[en_term.strip()] = th_translation.strip()
        return glossary
    except Exception as e:
        if isinstance(e, ValueError):
            raise
        raise ValueError(f"Error loading glossary: {str(e)}")

def replace_with_dictionary(text: str, dictionary: dict[str, str]) -> str:
    """
    Replaces internal Wikipedia links in the text with translations from the dictionary.

    Args:
        text: The input text.
        dictionary: A dictionary mapping English titles to Thai translations.

    Returns:
        The text with replaced links.
    """
    pattern = r"\[\[(?!File:)(?:([^#|\]]+)(?:#[^|\]]*)?(?:\|([^\]]+))?)\]\]"
    replaced = text
    for match in re.findall(pattern, text):
        original_link = match[0]
        display_text = match[1] if match[1] else original_link

        if display_text != original_link:
             # Translate display text if it's different from the link target
            translated_display_text = translate_text(display_text)
            replaced = replaced.replace(display_text, translated_display_text)

        replacement = dictionary.get(original_link)
        if replacement:
            replaced = replaced.replace(original_link, replacement)
        else:
            # If not in dictionary, translate the original link target
            translated_original_link = translate_text(original_link)
            replaced = replaced.replace(original_link, translated_original_link)

    return replaced

def replace_image_des(text: str, dictionary: dict[str, str]) -> str:
    """
    Replaces the description in a Wikipedia image tag with a translated version.

    Args:
        text: The input text containing the image tag.
        dictionary: A dictionary for translating links within the description.

    Returns:
        The text with the translated image description.
    """
    pattern = r"\[{2}File:.*?(?:\|.*\|)(.*|\n*?|[^\]]*)\]{2}(?=\n)"
    match = re.search(pattern, text)
    if match:
        description = match.group(1)
        # Translate the description, including any links within it
        translated_description = translate_text(replace_with_dictionary(description, dictionary))
        # Replace the original description with the translated one and change 'File:' to 'ไฟล์:'
        return text.replace(description, translated_description).replace('File:', 'ไฟล์:')
    return text # Return original text if no image tag found

def replace_quote(text: str, dictionary: dict[str, str]) -> str:
    """
    Replaces the content of a blockquote or quote template with a translated version.

    Args:
        text: The input text containing the quote template.
        dictionary: A dictionary for translating links within the quote.

    Returns:
        The text with the translated quote content.
    """
    pattern = r"\{\{(?:blockquote|quote)\|(.*)\}\}"
    match = re.search(pattern, text, flags=re.DOTALL)
    if match:
        quote_content = match.group(1)
        # Translate the quote content, including any links within it
        translated_quote_content = translate_text(replace_with_dictionary(quote_content, dictionary))
        return text.replace(quote_content, translated_quote_content)
    return text # Return original text if no quote template found

def replace_bullet_point(text: str, dictionary: dict[str, str]) -> str:
    """
    Translates the text content of a bullet point, handling internal links.

    Args:
        text: The input text representing a bullet point.
        dictionary: A dictionary for translating links within the bullet point.

    Returns:
        The bullet point text with translated content.
    """
    pattern = r"^[•\*]+\s*(.*)"
    match = re.search(pattern, text)
    if match:
        bullet_content = match.group(1)
        # Translate the bullet point content, including any links within it
        translated_content = translate_text(replace_with_dictionary(bullet_content, dictionary))
        return text.replace(bullet_content, translated_content)
    return text # Return original text if no bullet point match

def read_file(file_path: str) -> str:
    """
    Reads the content of a file.

    Args:
        file_path: The path to the file.

    Returns:
        The content of the file as a string.
        
    Raises:
        ValueError: If the file path is invalid or attempts path traversal.
    """
    try:
        # Convert to absolute path and check if it's within the current directory
        abs_path = os.path.abspath(file_path)
        base_dir = os.path.abspath(os.getcwd())
        
        if not abs_path.startswith(base_dir):
            raise ValueError(f"Access denied: File path must be within the application directory")
        
        # Ensure the file exists
        if not os.path.isfile(abs_path):
            raise ValueError(f"File not found: {file_path}")
            
        with open(abs_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        if isinstance(e, ValueError):
            raise
        raise ValueError(f"Error reading file: {str(e)}")

def remove_comments(text: str) -> str:
    """
    Removes HTML comments from the text.

    Args:
        text: The input text.

    Returns:
        The text with HTML comments removed.
    """
    pattern = r"<!--[^\>]*>"
    return re.sub(pattern, "", text, flags=re.DOTALL)

if __name__ == "__main__":
    # Example usage for replace_image_des
    TEST_IMAGE_TAG = "[[File:Najib Razak 2008-08-21.jpg|thumb|[[Najib Razak]], the former [[Prime Minister of Malaysia]], faced allegations of involvement in a large-scale financial scandal related to the state investment fund [[1Malaysia Development Berhad]] (1MDB).]]"
    # Need a mock dictionary and translate_text function for this example to run
    # mock_dictionary = {"Najib Razak": "นาจิบ ราซะก์", "Prime Minister of Malaysia": "นายกรัฐมนตรีมาเลเซีย"}
    # def mock_translate_text(text_or_list):
    #     if isinstance(text_or_list, str):
    #         return mock_dictionary.get(text_or_list, text_or_list)
    #     elif isinstance(text_or_list, list):
    #         return [mock_dictionary.get(item, item) for item in text_or_list]
    #
    # translated_image_des = replace_image_des(TEST_IMAGE_TAG, mock_dictionary)
    # print(f"Translated image description: {translated_image_des}")

    # Example usage for replace_quote
    TEST_QUOTE = "{{blockquote|This is a test quote with a [[link]].}}"
    # Need a mock dictionary and translate_text function for this example to run
    # mock_dictionary = {"link": "ลิงก์"}
    # def mock_translate_text(text_or_list):
    #     if isinstance(text_or_list, str):
    #         return mock_dictionary.get(text_or_list, text_or_list)
    #     elif isinstance(text_or_list, list):
    #         return [mock_dictionary.get(item, item) for item in text_or_list]
    #
    # translated_quote = replace_quote(TEST_QUOTE, mock_dictionary)
    # print(f"Translated quote: {translated_quote}")

    # Example usage for replace_bullet_point
    TEST_BULLET = "* This is a bullet point with a [[link]]."
    # Need a mock dictionary and translate_text function for this example to run
    # mock_dictionary = {"link": "ลิงก์"}
    # def mock_translate_text(text_or_list):
    #     if isinstance(text_or_list, str):
    #         return mock_dictionary.get(text_or_list, text_or_list)
    #     elif isinstance(text_or_list, list):
    #         return [mock_dictionary.get(item, item) for item in text_or_list]
    #
    # translated_bullet = replace_bullet_point(TEST_BULLET, mock_dictionary)
    # print(f"Translated bullet point: {translated_bullet}")

    pass # Placeholder for potential future test code

def replace_references(text: str, ref_map: dict[str, str]) -> str:
    """
    Replaces reference placeholders in the text with the original reference tags.

    Args:
        text: The input text with reference placeholders.
        ref_map: A dictionary mapping placeholders to original reference tags.

    Returns:
        The text with original reference tags restored.
    """
    def replacement(match):
        ref_number = match.group(0)
        return ref_map.get(ref_number, ref_number)  # Default to original placeholder if not found

    pattern = r"\[(\d+)\]"
    return re.sub(pattern, replacement, text)