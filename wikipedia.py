import re
import requests
import json

class Wikipedia:
    """
    A class to fetch and process Wikipedia page content.
    """
    def __init__(self, title_name: str) -> None:
        """
        Initializes the Wikipedia object by fetching page data.

        Args:
            title_name: The title of the Wikipedia page to fetch.
        """
        self.title_name = title_name
        self.page = self.__fetch_page(self.title_name)
        self.wikitext = self.__get_wikitext(self.page)
        self.wikilinks = self.__get_internal_links(self.page)
        self.wikitext_no_ref, self.ref_map = self.__pull_ref_tag(self.wikitext)
        self.dictonary, self.no_th_titles = self.__map_th_title(titles=self.wikilinks, source_lang="en", target_lang="th")

    def __fetch_page(self, title_name: str) -> dict:
        """
        Fetches the Wikipedia page content using the MediaWiki API.

        Args:
            title_name: The title of the Wikipedia page.

        Returns:
            A dictionary containing the parsed page data.
        """
        url = "https://en.wikipedia.org/w/api.php"
        param = {
            "action": "parse",
            "format": "json",
            "page": title_name,
            "prop": "links|wikitext",
            "formatversion": "2"
        }

        response = requests.get(url, params=param)
        data = response.json()
        return data["parse"]

    def __get_wikitext(self, page: dict) -> str:
        """
        Extracts the wikitext content from the parsed page data.

        Args:
            page: The parsed page data dictionary.

        Returns:
            The wikitext content as a string.
        """
        return page["wikitext"]

    def __get_internal_links(self, page: dict) -> list[str]:
        """
        Extracts internal links (titles) from the parsed page data.

        Args:
            page: The parsed page data dictionary.

        Returns:
            A list of internal link titles.
        """
        return [link['title'] for link in page.get("links", [])] # Handle missing 'links' key

    def __pull_ref_tag(self, wikitext: str) -> tuple[str, dict[str, str]]:
        """
        Extracts reference tags from wikitext and replaces them with placeholders.

        Args:
            wikitext: The input wikitext string.

        Returns:
            A tuple containing the wikitext with references replaced by placeholders
            and a dictionary mapping placeholders to original reference tags.
        """
        ref_map = {}
        ref_count: int = 1

        def replacement(match):
            nonlocal ref_count
            ref_number = f"[{ref_count}]"
            ref_map[ref_number] = match.group(0)
            ref_count += 1
            return ref_number

        pattern = r"<ref(?:[^>]*)?>(?:[^<]*<\/ref>)?"
        result = re.sub(pattern, replacement, wikitext)
        return result, ref_map

    def __map_th_title(self, titles: list[str], source_lang: str, target_lang: str) -> tuple[dict[str, str], set[str]]:
        """
        Maps English Wikipedia titles to their Thai equivalents using the API.

        Args:
            titles: A list of English titles.
            source_lang: The source language code (e.g., "en").
            target_lang: The target language code (e.g., "th").

        Returns:
            A tuple containing a dictionary mapping English titles to Thai translations
            and a set of titles that could not be translated.
        """
        assert isinstance(titles, list), "The titles object is not a list"

        url = f"https://{source_lang}.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "titles": "",
            "prop": "langlinks",
            "lllang": target_lang,
            "redirects": 1,
            "format": "json"
        }

        title_mapping = {}
        no_th_titles = set() # Use a set for efficiency

        def process_response(data):
            pages = data.get('query', {}).get('pages', {})
            for page_data in pages.values(): # Iterate over values directly
                en_title = page_data.get('title')
                if en_title: # Ensure title exists
                    if 'langlinks' in page_data and page_data['langlinks']:
                        th_title = page_data['langlinks'][0].get('*') # Use .get for safety
                        if th_title: # Ensure translation exists
                            title_mapping[en_title] = th_title
                        else:
                            no_th_titles.add(en_title)
                    else:
                        no_th_titles.add(en_title)

        def query(request):
            last_continue = {}
            while True:
                req = request.copy()
                req.update(last_continue)
                response = requests.get(url, params=req)

                try:
                    result = response.json()
                except json.JSONDecodeError:
                    print("Warning: Received malformed JSON response, skipping.")
                    continue

                if 'error' in result:
                    raise Exception(result['error'])
                if 'warnings' in result:
                    print(result['warnings'])
                if 'query' in result:
                    process_response(result)
                if 'continue' not in result:
                    break
                last_continue = result.get('continue', {}) # Use .get for safety

        # Split the titles into batches of 50 and make the requests
        for i in range(0, len(titles), 50):
            batch = titles[i:i+50]
            params.update({"titles": "|".join(batch)})
            query(params)

        return title_mapping, no_th_titles

    def replace_references(self, texts: str) -> str:
        """
        Replaces reference placeholders in the text with the original reference tags.

        Args:
            texts: The input text with reference placeholders.

        Returns:
            The text with original reference tags restored.
        """
        def replacement(match):
            ref_number = match.group(0)
            return self.ref_map.get(ref_number, ref_number)  # Default to original placeholder if not found

        pattern = r"\[(\d+)\]"
        return re.sub(pattern, replacement, texts)

    @staticmethod
    def convert_to_list(text: str) -> list[str]:
        """
        Extracts non-empty lines from Wikitext, handling specific patterns.

        Args:
            text: The Wikitext string.

        Returns:
            A list of non-empty lines.
        """
        # This regex attempts to split the wikitext into meaningful blocks.
        # It's complex and might need further refinement based on specific wikitext structures.
        pattern = r"^.*\n*(?:\s?\|.*|\*\s*\[*.*\n?|\s?\}.*|\{\|.*|!.*|\(.*)*\s*\n*"
        matches = re.findall(pattern, text, flags=re.MULTILINE)
        return [match.strip() for match in matches if match.strip()] # Filter out empty strings

if __name__ == "__main__":
    # Example usage:
    # try:
    #     title_name = "Performance indicator"
    #     page = Wikipedia(title_name)
    #     print(f"Wikitext (no refs): {page.wikitext_no_ref[:200]}...") # Print first 200 chars
    #     print(f"References map: {page.ref_map}")
    #     print(f"Wikilinks: {page.wikilinks[:10]}...") # Print first 10 links
    #     print(f"Dictionary: {page.dictonary}")
    #     print(f"Titles without Thai translation: {page.no_th_titles}")
    #
    #     # Example of using replace_references
    #     text_with_placeholders = "This is some text with a reference[1]."
    #     restored_text = page.replace_references(text_with_placeholders)
    #     print(f"Text with references restored: {restored_text}")
    #
    #     # Example of using convert_to_list
    #     sample_wikitext = """
    #     == Section 1 ==
    #     This is some text.
    #
    #     * Bullet point 1
    #     * Bullet point 2
    #
    #     {{Template|arg1}}
    #
    #     [[Category:Example]]
    #     """
    #     wikitext_list = Wikipedia.convert_to_list(sample_wikitext)
    #     print(f"Wikitext converted to list: {wikitext_list}")
    #
    # except Exception as e:
    #     print(f"An error occurred: {e}")
    pass # Placeholder for potential future test code