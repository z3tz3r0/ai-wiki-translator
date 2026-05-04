# Plan: Transliteration Rule Scraper Foundation (Phase 1)

## Summary

Build the data-layer foundation for the transliteration quality gate · a `WikipediaTransliterationRuleSource` adapter, a `wiki-refresh-rules` CLI, a BS4-based parser, and a JSON cache writer. After this phase, future translations can read structured rule data from `~/.cache/wiki-translator/rules/<lang>.json` and the validator (Phase 2) has rule excerpts to feed the LLM-judge.

## User Story

As Kittipan (the wiki-translate user), I want to refresh the th.wiki transliteration-rule cache once with `wiki-refresh-rules`, so that future translations can validate foreign-name transliterations against rule excerpts without me opening browser tabs.

## Problem → Solution

**Current state:** `wiki-translate` passes Gemini a soft instruction (`ทับศัพท์ไทยที่เป็นที่ยอมรับ`, `app/prompts/system_instruction_th.md:15`) with no enforcement. The th.wiki rule pages exist as human-readable HTML on `th.wikipedia.org` but nothing in the codebase consumes them.

**Desired state:** A separate, manual `wiki-refresh-rules` CLI command scrapes the th.wiki rule pages once (per language or all-at-once), parses them into structured `LanguageRuleSet` JSON, and writes the result to `~/.cache/wiki-translator/rules/<lang>.json`. Phase 2's validator reads from the cache; Phase 3 wires the gate into `TranslateArticleUseCase`.

## Metadata

- **Complexity:** Medium · 3 new source files, 4 file updates, ~600 LOC including tests, no new architectural pattern (mirrors existing httpx adapter shape)
- **Source PRD:** `.claude/PRPs/prds/transliteration-quality-gate.prd.md`
- **PRD Phase:** Phase 1 · Rule scraper foundation
- **Estimated Files:** 9 (3 create, 5 update, 1 test fixture)

---

## UX Design

### Before

```
$ wiki-translate "ภาษาซีชาร์ป"
... 51 minutes later ...
draft saved · ~/Documents/wiki-translations/2026-05-04/ภาษาซีชาร์ป/

$ cat ภาษาซีชาร์ป.review.md
# Translation Draft Review · en
## Source ...
## Quality Gate
- status: passed
## Diff
```diff ... ```

# (no transliteration verdict · user must manually verify
#  every "แอนเดอส์ เฮลส์เบิร์ก" against th.wiki rule pages)
```

### After (Phase 1 only · the cache exists, gate not yet wired)

```
$ wiki-refresh-rules --lang en
2026-05-05 12:00:00 INFO app.application.use_cases.refresh_rules · refreshing rules for langs: ['en']
2026-05-05 12:00:01 INFO app.infrastructure.transliteration_rules · fetching https://th.wikipedia.org/w/api.php?action=parse&page=วิกิพีเดีย:คู่มือการเขียน/การทับศัพท์ภาษาอังกฤษ&prop=text
2026-05-05 12:00:02 INFO app.application.use_cases.refresh_rules · parsed 67 rule entries for en, wrote ~/.cache/wiki-translator/rules/en.json (12834 bytes)
done · 1 lang refreshed

$ jq '.entries | length' ~/.cache/wiki-translator/rules/en.json
67

$ jq '.entries[0]' ~/.cache/wiki-translator/rules/en.json
{
  "grapheme": "a",
  "thai": "เอ",
  "notes": "เมื่อใช้เป็นเสียงสระสั้นในพยางค์เปิด"
}
```

### Interaction Changes

| Touchpoint | Before | After | Notes |
|---|---|---|---|
| `wiki-refresh-rules --lang <code>` | does not exist | refreshes cache for one language | fails if `<code>` not in `LANG_TO_TITLE` map |
| `wiki-refresh-rules --all` | does not exist | refreshes cache for every supported language sequentially | continues past per-language failures, reports summary at end |
| `~/.cache/wiki-translator/rules/<lang>.json` | does not exist | structured rule-set JSON | atomic rename (`*.tmp` → final) so a partial scrape never corrupts an existing cache |
| `WIKI_TRANSLATOR_RULES_DIR` | not read | overrides default cache dir | mirrors existing `WIKI_TRANSLATOR_OUTPUT_DIR` pattern |

---

## Mandatory Reading

| Priority | File | Lines | Why |
|---|---|---|---|
| P0 (critical) | `app/infrastructure/wikipedia_http.py` | 1-104 | exact httpx adapter shape to mirror · transport-injectable, frozen dataclass, `_client(lang)` helper |
| P0 (critical) | `app/application/ports.py` | 1-84 | how protocols are declared (runtime_checkable, async signatures, doc-comment style) |
| P0 (critical) | `app/application/dto.py` | 1-69 | how DTOs are framed (frozen dataclass, primitives + tuples + Literal, no Mapping) |
| P0 (critical) | `app/interfaces/cli/main.py` | 33-100, 102-148 | logging setup, notify-completion shape, Typer command pattern, error path |
| P0 (critical) | `app/interfaces/cli/bootstrap.py` | 1-104 | env-var resolution, lazy SDK imports, `build_*_use_case` factory pattern |
| P1 (important) | `app/infrastructure/markdown_draft_storage.py` | 1-109 | file-IO adapter pattern · `asyncio.to_thread` wrapping, slug validation, `_backup_if_exists` atomicity |
| P1 (important) | `tests/infrastructure/test_wikipedia_http.py` | 1-208 | mock-transport test pattern · `_make_transport`, integration-marker convention |
| P1 (important) | `app/application/use_cases/translate_article.py` | 100-205, 335-360 | use-case shape (frozen dataclass with port fields), `_render_review_md` (Phase 3 will extend this) |
| P2 (reference) | `app/infrastructure/wikidata_http.py` | 1-121 | second httpx adapter for variation in patterns (e.g., dispatch-by-substring transport for tests) |
| P2 (reference) | `tests/conftest.py` | 1-24 | `_no_notify` autouse fixture (already silences notify-send in tests) |
| P2 (reference) | `pyproject.toml` | 1-100 | where to add bs4/lxml deps and the new `[project.scripts]` entry |

## External Documentation

| Topic | Source | Key Takeaway |
|---|---|---|
| MediaWiki action=parse | https://www.mediawiki.org/wiki/API:Parsing_wikitext | use `prop=text` for HTML; response payload is `parse.text` (string of HTML). Has `redirects=1` for safe title resolution. |
| BeautifulSoup4 + lxml | https://www.crummy.com/software/BeautifulSoup/bs4/doc/ | parser kwarg `lxml` (faster, lenient than `html.parser`); `find_all("table", class_="wikitable")` is standard for MediaWiki table extraction |
| th.wiki parent rule index | https://th.wikipedia.org/wiki/หลักเกณฑ์การทับศัพท์ของราชบัณฑิตยสถานและสำนักงานราชบัณฑิตยสภา | wikitable enumerates per-language rule pages · MUST be `WebFetch`ed at Task 1 to populate `LANG_TO_TITLE` |
| th.wiki English rule page | https://th.wikipedia.org/wiki/วิกิพีเดีย:คู่มือการเขียน/การทับศัพท์ภาษาอังกฤษ | the source-of-truth child page · the parser MUST handle this layout in Phase 1 |
| atomic file write idiom (Python) | https://docs.python.org/3.13/library/os.html#os.rename | `os.rename(tmp, final)` is atomic on POSIX when same filesystem; same convention used by `_backup_if_exists` in markdown_draft_storage.py:102-108 |

---

## Patterns to Mirror

Code patterns discovered in the codebase. Follow these exactly · do not invent new shapes.

### PROTOCOL_DEFINITION
```python
# SOURCE: app/application/ports.py:14-20
@runtime_checkable
class WikipediaReader(Protocol):
    """Read-only access to MediaWiki API across language wikis."""

    async def fetch_article(self, title: str, lang: str) -> Article | None: ...

    async def fetch_langlinks(self, title: str, lang: str) -> dict[str, str]: ...
```
Apply: `TransliterationRuleSource` follows the same shape · `@runtime_checkable Protocol`, async method, single-line docstring before the protocol body, returns a DTO.

### HTTP_ADAPTER
```python
# SOURCE: app/infrastructure/wikipedia_http.py:24-103
DEFAULT_USER_AGENT = "ai-wiki-translator/0.1 (https://github.com/z3tz3r0/ai-wiki-translator)"


@dataclass(frozen=True)
class WikipediaHttpReader:
    """`WikipediaReader` Protocol implementation backed by the live MediaWiki API."""

    transport: httpx.AsyncBaseTransport | None = None
    user_agent: str = DEFAULT_USER_AGENT
    timeout: float = 30.0

    async def fetch_article(self, title: str, lang: str) -> Article | None:
        data = await self._get_parse(title, lang, prop="wikitext")
        # ...

    def _client(self, lang: str) -> httpx.AsyncClient:
        kwargs: dict[str, Any] = {
            "base_url": f"https://{lang}.wikipedia.org",
            "headers": {"User-Agent": self.user_agent},
            "timeout": self.timeout,
        }
        if self.transport is not None:
            kwargs["transport"] = self.transport
        return httpx.AsyncClient(**kwargs)
```
Apply: `WikipediaTransliterationRuleSource` mirrors this dataclass shape exactly · transport-injectable for tests, frozen, has a `_client()` helper that pins to `https://th.wikipedia.org` (because rules are always on th.wiki, never on per-source-lang wikis · this is the key difference from `WikipediaHttpReader`).

### MOCK_TRANSPORT_TEST
```python
# SOURCE: tests/infrastructure/test_wikipedia_http.py:16-34
def _make_transport(
    routes: dict[tuple[str, str], dict[str, Any]],
) -> httpx.MockTransport:
    """Map ``(host, page)`` -> response JSON.

    Falls through to ``{"error": {"code": "missingtitle"}}`` for unknown pages.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path != "/w/api.php":
            return httpx.Response(404, json={"error": {"code": "unknown-endpoint"}})
        page = request.url.params.get("page", "")
        host = request.url.host
        body = routes.get((host, page))
        if body is None:
            return httpx.Response(200, json={"error": {"code": "missingtitle"}})
        return httpx.Response(200, json=body)

    return httpx.MockTransport(handler)
```
Apply: `tests/infrastructure/test_transliteration_rules.py` uses an analogous `_make_transport` that returns HTML strings (not JSON-encoded responses · the response body is HTML wrapped inside the JSON `parse.text` field).

### FILE_IO_ASYNC_WRAP
```python
# SOURCE: app/infrastructure/markdown_draft_storage.py:37-60
async def save_draft(
    self,
    slug: str,
    wikitext: str,
    review_md: str,
    when: datetime.datetime,
) -> Path:
    _validate_slug(slug)
    date_iso = when.date().isoformat()
    out_dir = self.base_dir / date_iso / slug
    await asyncio.to_thread(self._save_sync, out_dir, slug, wikitext, review_md)
    return out_dir

def _save_sync(self, out_dir: Path, slug: str, wikitext: str, review_md: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    wikitext_path = out_dir / f"{slug}.wikitext"
    review_path = out_dir / f"{slug}.review.md"
    _backup_if_exists(wikitext_path)
    _backup_if_exists(review_path)
    wikitext_path.write_text(wikitext, encoding="utf-8")
    review_path.write_text(review_md, encoding="utf-8")
```
Apply: cache reader/writer functions in `transliteration_rules.py` follow the same `asyncio.to_thread(_sync_fn, ...)` wrapping. UTF-8 encoding explicit. Atomic-rename for safety.

### USE_CASE_DATACLASS
```python
# SOURCE: app/application/use_cases/translate_article.py:100-115
@dataclass(frozen=True)
class TranslateArticleUseCase:
    wikipedia: WikipediaReader
    wikidata: WikidataReader
    machine: MachineTranslator
    llm: LLMTranslator
    prompt_repo: PromptTemplateRepository
    glossary_repo: GlossaryRepository
    storage: DraftStorage
    quality_gate: QualityGate = field(default_factory=QualityGate)
    target_lang: str = "th"
    locale_to_lang: dict[str, str] = field(default_factory=dict)
    prompt_template_id: str = "system_instruction_th"
    clock: Callable[[], datetime] = _utcnow_naive

    async def execute(self, cmd: TranslateArticleCommand) -> Draft:
        ...
```
Apply: `RefreshRulesUseCase` is a frozen dataclass with one port (`source: TransliterationRuleSource`) and one config field (`rules_dir: Path`). Single `execute(langs: Sequence[str])` method.

### CLI_TYPER_APP
```python
# SOURCE: app/interfaces/cli/main.py:54-56, 102-148
translate_app = typer.Typer(add_completion=False, no_args_is_help=True)


@translate_app.command()
def translate(
    title: Annotated[
        str,
        typer.Argument(help="Thai-Wikipedia article title to translate."),
    ],
    source_lang: Annotated[
        str | None,
        typer.Option("--source-lang", help="Force a source language (skips auto picker).",),
    ] = None,
    # ...
) -> None:
    """Translate one article and write a review-ready draft to disk."""
    cmd = TranslateArticleCommand(...)
    try:
        use_case = bootstrap.build_translate_use_case(output_dir=output_dir)
        draft = asyncio.run(use_case.execute(cmd))
    except Exception as exc:
        typer.echo(f"error: {exc}", err=True)
        _notify_completion("wiki-translate failed", str(exc))
        raise typer.Exit(code=1) from exc
    _print_draft(draft)
    _notify_completion("wiki-translate done", _format_draft_summary(draft))
```
Apply: `refresh_rules_app` is a separate `typer.Typer(add_completion=False, no_args_is_help=True)` instance with one `@app.command()`-decorated function. Wraps `bootstrap.build_refresh_rules_use_case()` in try/except, calls `_notify_completion` on both success and failure, raises `typer.Exit(code=1) from exc` on error.

### BOOTSTRAP_FACTORY
```python
# SOURCE: app/interfaces/cli/bootstrap.py:101-103
def build_list_drafts_use_case(*, output_dir: Path | None = None) -> ListDraftsUseCase:
    """Wire `ListDraftsUseCase` with the on-disk draft store."""
    return ListDraftsUseCase(storage=MarkdownDraftStorage(base_dir=_resolve_output_dir(output_dir)))
```
Apply: `build_refresh_rules_use_case(*, rules_dir: Path | None = None)` is a one-liner (no Gemini key needed · `wiki-refresh-rules` is network-only). Pairs with `_resolve_rules_dir(override) -> Path` env-resolver helper.

### LOGGING_PATTERN
```python
# SOURCE: app/application/use_cases/translate_article.py:57, 117-135
logger = logging.getLogger(__name__)

# inside execute():
logger.info("translating %r (slug=%s, target=%s)", cmd.title, slug, self.target_lang)
logger.info("found %d langlinks for %r", len(langlinks), cmd.title)
logger.warning("source pick failed: %s", exc)
```
Apply: every new module gets `logger = logging.getLogger(__name__)` immediately after imports. Use `%r` for user-supplied strings, `%s` for system identifiers, `%d` for counts. Lazy-format (no f-strings inside log calls · `%`-style lets the logging machinery skip formatting for filtered-out levels).

---

## Files to Change

| File | Action | Justification |
|---|---|---|
| `app/application/dto.py` | UPDATE | append `RuleEntry` and `LanguageRuleSet` dataclasses |
| `app/application/ports.py` | UPDATE | append `TransliterationRuleSource` Protocol |
| `app/application/use_cases/refresh_rules.py` | CREATE | new use case orchestrating fetch + cache write |
| `app/infrastructure/transliteration_rules.py` | CREATE | new HTTP adapter `WikipediaTransliterationRuleSource` + module-level cache helpers |
| `app/interfaces/cli/main.py` | UPDATE | add `refresh_rules_app` Typer instance and `refresh_rules` command |
| `app/interfaces/cli/bootstrap.py` | UPDATE | add `_resolve_rules_dir`, `build_refresh_rules_use_case` |
| `pyproject.toml` | UPDATE | add `beautifulsoup4`, `lxml` deps; add `wiki-refresh-rules` script entry |
| `tests/infrastructure/test_transliteration_rules.py` | CREATE | mock-transport adapter tests + cache roundtrip tests |
| `tests/interfaces/cli/test_refresh_rules.py` | CREATE | CliRunner smoke tests with monkeypatched bootstrap |
| `tests/application/test_refresh_rules.py` | CREATE | use-case tests with `FakeTransliterationRuleSource` |
| `tests/fakes/transliteration.py` | CREATE | `FakeTransliterationRuleSource` for use-case + integration tests |
| `tests/fixtures/transliteration_rules/en.html` | CREATE | sample MediaWiki-rendered HTML excerpt for parser tests |

## NOT Building

- **The validator.** No `TransliterationValidator` port, no LLM-judge wiring, no Gemini calls. That's Phase 2.
- **The detector.** No regex for finding candidate transliterations in proposed wikitext. Phase 2.
- **Integration into `TranslateArticleUseCase`.** No changes to `_render_review_md`, no new section in review.md. Phase 3.
- **Wunsen / Royal-Society-publication scrapers.** PRD locks th.wiki as sole source of truth. Out of scope.
- **Cron / scheduled refresh.** Manual command only. PRD line 29.
- **Rule-page coverage beyond what the parent index lists.** If th.wiki has no per-language page for some source language, `wiki-refresh-rules --lang <missing>` returns a clean error · soft-degrade is Phase 3's concern.
- **Multi-language batched fetching in parallel.** Sequential is fine for v1 · `--all` runs langs one at a time. The parent index has ~10-20 languages, total runtime is seconds.
- **Last-known-good fallback when th.wiki edits a page and the parser breaks.** PRD lists this as Phase 2+ mitigation. v1 surfaces parse failures explicitly.

---

## Step-by-Step Tasks

### Task 0: Add dependencies + script entry
- **ACTION:** Update `pyproject.toml`
- **IMPLEMENT:**
  ```toml
  # in [project] dependencies, alphabetical:
  "beautifulsoup4>=4.12.3",
  "lxml>=5.3.0",

  # in [project.scripts], after the three existing entries:
  wiki-refresh-rules = "app.interfaces.cli.main:refresh_rules_app"
  ```
- **MIRROR:** existing dep list shape and `[project.scripts]` block
- **IMPORTS:** none
- **GOTCHA:** must run `uv sync` after edit; pre-commit will block commit otherwise. `uv.lock` updates automatically.
- **VALIDATE:** `uv sync && uv run python -c "import bs4, lxml; print(bs4.__version__, lxml.__version__)"`

### Task 1: Discover the LANG_TO_TITLE map
- **ACTION:** WebFetch the parent index page, hand-build a static dict in `app/infrastructure/transliteration_rules.py`
- **IMPLEMENT:** Use `WebFetch("https://th.wikipedia.org/wiki/หลักเกณฑ์การทับศัพท์ของราชบัณฑิตยสถานและสำนักงานราชบัณฑิตยสภา", "List every language and the link to its rule page on th.wiki")`. Read the wikitable rows · each row has a Thai language name and a link to a rule page like `วิกิพีเดีย:คู่มือการเขียน/การทับศัพท์ภาษาอังกฤษ`. Build:
  ```python
  # app/infrastructure/transliteration_rules.py
  LANG_TO_TITLE: dict[str, str] = {
      "en": "วิกิพีเดีย:คู่มือการเขียน/การทับศัพท์ภาษาอังกฤษ",
      "fr": "...",
      "de": "...",
      "ja": "...",
      "es": "...",
      # ... fill from WebFetch result
  }
  ```
  Comment line above the dict cites the parent index URL and the date scraped.
- **MIRROR:** style of constants like `_PASSTHROUGH_TYPES` in `translate_article.py:89-97` · module-level, type-annotated.
- **IMPORTS:** none for the constant; WebFetch is build-time only.
- **GOTCHA:** the parent page may have BOTH the th.wiki style-guide variants (`วิกิพีเดีย:คู่มือการเขียน/...`) and the Royal Society academic pages. Use the th.wiki style-guide variant when available · "th.wiki rules as source of truth" per PRD Decisions Log.
- **VALIDATE:** dict has at least 5 entries (en + 4 others) and every value starts with `วิกิพีเดีย:` or `หลักเกณฑ์การทับศัพท์`. Print the dict; spot-check three entries against the parent page wikitable in a browser.

### Task 2: Define DTOs
- **ACTION:** Append to `app/application/dto.py`
- **IMPLEMENT:**
  ```python
  @dataclass(frozen=True)
  class RuleEntry:
      """One grapheme · its Thai transliteration · optional notes.

      Source-language graphemes (English digraphs, French liaisons, etc.)
      paired with the Thai script the rule prescribes.
      """

      grapheme: str
      thai: str
      notes: str = ""


  @dataclass(frozen=True)
  class LanguageRuleSet:
      """Cached th.wiki transliteration rules for one source language.

      Phase 1 writes one of these to ~/.cache/wiki-translator/rules/<lang>.json
      after scraping. Phase 2's validator will read it back at translation time.
      The `excerpt` is a markdown rendering of the rule page suitable for
      pasting into an LLM-judge prompt; `entries` is the structured form for
      direct lookup.
      """

      lang: str
      title: str
      url: str
      scraped_at: datetime.datetime
      entries: tuple[RuleEntry, ...]
      excerpt: str
  ```
  Add `import datetime` to top of `dto.py` if not already imported (it is · line 5).
- **MIRROR:** `Draft` and `ReviewNotes` patterns at `dto.py:30-58` · frozen, primitives + tuple, multi-line docstring with WHY context.
- **IMPORTS:** `datetime` already imported.
- **GOTCHA:** use `tuple[RuleEntry, ...]` not `list[RuleEntry]` · matches existing `validation: tuple[str, ...]` and `wikilinks: tuple[str, ...]` immutability convention.
- **VALIDATE:** `uv run mypy app/application/dto.py` zero errors.

### Task 3: Define the port
- **ACTION:** Append to `app/application/ports.py`
- **IMPLEMENT:**
  ```python
  from app.application.dto import DraftMetadata, LanguageRuleSet  # update existing import


  @runtime_checkable
  class TransliterationRuleSource(Protocol):
      """Fetches th.wiki transliteration rule pages for one source language.

      Adapters parse the live MediaWiki HTML response and return a structured
      `LanguageRuleSet`. The CLI command `wiki-refresh-rules` invokes this
      port and persists the result to a JSON cache. Phase 3's gate reads the
      cache directly · this port is fetch-only.
      """

      async def fetch(self, lang: str) -> LanguageRuleSet: ...
  ```
- **MIRROR:** `WikipediaReader` at `ports.py:14-20` · `@runtime_checkable Protocol`, single async method, multi-line docstring describing scope.
- **IMPORTS:** `LanguageRuleSet` from `app.application.dto`.
- **GOTCHA:** the docstring should clarify that the port is FETCH-ONLY (no cache IO) so future maintainers don't expect persistence semantics here. Persistence lives in module-level helpers in the adapter file.
- **VALIDATE:** `uv run mypy app/application/ports.py` zero errors. `uv run python -c "from app.application.ports import TransliterationRuleSource; print(TransliterationRuleSource.__doc__)"`.

### Task 4: Implement the adapter
- **ACTION:** Create `app/infrastructure/transliteration_rules.py`
- **IMPLEMENT:**
  ```python
  """WikipediaTransliterationRuleSource · th.wiki rule-page scraper via httpx + BS4.

  Hits ``https://th.wikipedia.org/w/api.php`` with ``action=parse&prop=text``
  to get pre-rendered HTML for a rule page (templates expanded by the server),
  then parses the wikitables to extract grapheme→Thai entries. The free
  functions `read_cache` and `write_cache` handle on-disk persistence as
  ``~/.cache/wiki-translator/rules/<lang>.json``.
  """

  from __future__ import annotations

  import asyncio
  import datetime
  import json
  import logging
  import os
  import tempfile
  from dataclasses import dataclass
  from pathlib import Path
  from typing import Any

  import httpx
  from bs4 import BeautifulSoup

  from app.application.dto import LanguageRuleSet, RuleEntry

  logger = logging.getLogger(__name__)

  DEFAULT_USER_AGENT = "ai-wiki-translator/0.1 (https://github.com/z3tz3r0/ai-wiki-translator)"
  RULE_HOST = "https://th.wikipedia.org"

  # Static map; populated from a 2026-05-05 WebFetch of
  # https://th.wikipedia.org/wiki/หลักเกณฑ์การทับศัพท์ของราชบัณฑิตยสถานและสำนักงานราชบัณฑิตยสภา
  LANG_TO_TITLE: dict[str, str] = {
      "en": "วิกิพีเดีย:คู่มือการเขียน/การทับศัพท์ภาษาอังกฤษ",
      # ... fill from Task 1
  }


  class UnsupportedLanguage(ValueError):
      """Raised when `fetch(lang)` is called with a lang not in `LANG_TO_TITLE`."""


  class RulePageParseError(RuntimeError):
      """Raised when the rule page HTML can't be parsed into ≥1 RuleEntry."""


  @dataclass(frozen=True)
  class WikipediaTransliterationRuleSource:
      """`TransliterationRuleSource` Protocol implementation backed by live th.wiki."""

      transport: httpx.AsyncBaseTransport | None = None
      user_agent: str = DEFAULT_USER_AGENT
      timeout: float = 30.0

      async def fetch(self, lang: str) -> LanguageRuleSet:
          if lang not in LANG_TO_TITLE:
              raise UnsupportedLanguage(
                  f"no th.wiki rule page registered for lang={lang!r} · "
                  f"supported: {sorted(LANG_TO_TITLE)}"
              )
          title = LANG_TO_TITLE[lang]
          html = await self._fetch_parse_text(title)
          if html is None:
              raise RulePageParseError(
                  f"th.wiki returned no parse.text for {title!r} (lang={lang})"
              )
          entries, excerpt = _parse_rule_html(html)
          if not entries:
              raise RulePageParseError(
                  f"parsed 0 rule entries for lang={lang} title={title!r} · "
                  f"page layout may have changed"
              )
          logger.info("parsed %d rule entries for %s (title=%r)", len(entries), lang, title)
          return LanguageRuleSet(
              lang=lang,
              title=title,
              url=f"{RULE_HOST}/wiki/{title}",
              scraped_at=datetime.datetime.now(datetime.UTC).replace(tzinfo=None),
              entries=tuple(entries),
              excerpt=excerpt,
          )

      async def _fetch_parse_text(self, title: str) -> str | None:
          async with self._client() as client:
              response = await client.get(
                  "/w/api.php",
                  params={
                      "action": "parse",
                      "page": title,
                      "prop": "text",
                      "format": "json",
                      "formatversion": "2",
                      "redirects": "1",
                  },
              )
              response.raise_for_status()
              payload: dict[str, Any] = response.json()
          if "error" in payload:
              return None
          parse = payload.get("parse")
          if not isinstance(parse, dict):
              return None
          text = parse.get("text")
          return text if isinstance(text, str) else None

      def _client(self) -> httpx.AsyncClient:
          kwargs: dict[str, Any] = {
              "base_url": RULE_HOST,
              "headers": {"User-Agent": self.user_agent},
              "timeout": self.timeout,
          }
          if self.transport is not None:
              kwargs["transport"] = self.transport
          return httpx.AsyncClient(**kwargs)


  def _parse_rule_html(html: str) -> tuple[list[RuleEntry], str]:
      """Extract RuleEntry rows from one or more wikitables.

      Selector strategy (most-tolerant first):
        1. find every ``table.wikitable``
        2. for each table: skip the header row, expect at least 2 cells per
           row (grapheme, thai), optional 3rd cell as notes
        3. concatenate all rows into the entry list; preserve source order

      The excerpt is the markdown form of the first 3 tables (joined with
      blank lines), suitable for pasting into an LLM-judge prompt later.
      """
      soup = BeautifulSoup(html, "lxml")
      tables = soup.find_all("table", class_="wikitable")
      entries: list[RuleEntry] = []
      excerpt_parts: list[str] = []
      for table in tables:
          rows = table.find_all("tr")
          for row in rows[1:]:  # skip header
              cells = row.find_all(["td", "th"])
              if len(cells) < 2:
                  continue
              grapheme = cells[0].get_text(strip=True)
              thai = cells[1].get_text(strip=True)
              if not grapheme or not thai:
                  continue
              notes = cells[2].get_text(strip=True) if len(cells) >= 3 else ""
              entries.append(RuleEntry(grapheme=grapheme, thai=thai, notes=notes))
          if len(excerpt_parts) < 3:
              excerpt_parts.append(_table_to_markdown(table))
      excerpt = "\n\n".join(excerpt_parts)
      return entries, excerpt


  def _table_to_markdown(table: Any) -> str:
      """Render one BS4 `<table>` as a fenced markdown table for LLM prompts."""
      lines: list[str] = []
      for row in table.find_all("tr"):
          cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
          if not cells:
              continue
          lines.append("| " + " | ".join(cells) + " |")
          if len(lines) == 1:
              lines.append("|" + "|".join(["---"] * len(cells)) + "|")
      return "\n".join(lines)


  # --- cache helpers ------------------------------------------------------------


  def default_rules_dir() -> Path:
      """``~/.cache/wiki-translator/rules`` · honors ``XDG_CACHE_HOME`` if set."""
      xdg = os.environ.get("XDG_CACHE_HOME")
      base = Path(xdg) if xdg else Path.home() / ".cache"
      return base / "wiki-translator" / "rules"


  async def read_cache(rules_dir: Path, lang: str) -> LanguageRuleSet | None:
      return await asyncio.to_thread(_read_sync, rules_dir, lang)


  async def write_cache(rules_dir: Path, ruleset: LanguageRuleSet) -> Path:
      return await asyncio.to_thread(_write_sync, rules_dir, ruleset)


  def _read_sync(rules_dir: Path, lang: str) -> LanguageRuleSet | None:
      path = rules_dir / f"{lang}.json"
      if not path.is_file():
          return None
      try:
          payload = json.loads(path.read_text(encoding="utf-8"))
      except (OSError, json.JSONDecodeError) as exc:
          logger.warning("cache read failed for %s: %s · returning None", path, exc)
          return None
      return _from_dict(payload)


  def _write_sync(rules_dir: Path, ruleset: LanguageRuleSet) -> Path:
      rules_dir.mkdir(parents=True, exist_ok=True)
      final = rules_dir / f"{ruleset.lang}.json"
      with tempfile.NamedTemporaryFile(
          mode="w",
          encoding="utf-8",
          dir=rules_dir,
          delete=False,
          suffix=".tmp",
      ) as tmp:
          json.dump(_to_dict(ruleset), tmp, ensure_ascii=False, indent=2)
          tmp_path = Path(tmp.name)
      tmp_path.replace(final)  # atomic on POSIX same-fs
      return final


  def _to_dict(rs: LanguageRuleSet) -> dict[str, Any]:
      return {
          "lang": rs.lang,
          "title": rs.title,
          "url": rs.url,
          "scraped_at": rs.scraped_at.isoformat(),
          "entries": [
              {"grapheme": e.grapheme, "thai": e.thai, "notes": e.notes}
              for e in rs.entries
          ],
          "excerpt": rs.excerpt,
      }


  def _from_dict(d: dict[str, Any]) -> LanguageRuleSet | None:
      try:
          entries = tuple(
              RuleEntry(grapheme=e["grapheme"], thai=e["thai"], notes=e.get("notes", ""))
              for e in d["entries"]
          )
          return LanguageRuleSet(
              lang=d["lang"],
              title=d["title"],
              url=d["url"],
              scraped_at=datetime.datetime.fromisoformat(d["scraped_at"]),
              entries=entries,
              excerpt=d.get("excerpt", ""),
          )
      except (KeyError, TypeError, ValueError) as exc:
          logger.warning("cache deserialize failed: %s", exc)
          return None
  ```
- **MIRROR:** HTTP_ADAPTER and FILE_IO_ASYNC_WRAP patterns above. The structure mirrors `wikipedia_http.py` for the network half and `markdown_draft_storage.py` for the disk half.
- **IMPORTS:** as listed in the snippet · prefer stdlib + httpx + bs4. No aiofiles.
- **GOTCHA #1:** `prop=text` returns HTML, not wikitext · response shape is `{"parse": {"title": "...", "text": "<div>...</div>"}}`. The `text` field is a string of HTML, not a JSON-encoded HTML object.
- **GOTCHA #2:** the th.wiki rule pages have multiple wikitables on one page (one per phoneme group). Don't stop at the first table.
- **GOTCHA #3:** atomic rename only works when source and destination are on the same filesystem. We create the tempfile in `rules_dir` (same dir as the final), so this is guaranteed.
- **GOTCHA #4:** `BeautifulSoup(html, "lxml")` requires `lxml` installed. Without it BS4 silently falls back to `html.parser` which is slower and stricter. Task 0 added the dep · verify with `import lxml`.
- **GOTCHA #5:** `redirects=1` on the API call is mandatory · th.wiki uses redirect pages liberally for old/canonical title forms.
- **VALIDATE:** `uv run mypy app/infrastructure/transliteration_rules.py` zero errors. `uv run ruff check app/infrastructure/transliteration_rules.py` zero violations.

### Task 5: Implement RefreshRulesUseCase
- **ACTION:** Create `app/application/use_cases/refresh_rules.py`
- **IMPLEMENT:**
  ```python
  """RefreshRulesUseCase · scrape th.wiki rule pages and write JSON cache."""

  from __future__ import annotations

  import logging
  from collections.abc import Sequence
  from dataclasses import dataclass
  from pathlib import Path

  from app.application.ports import TransliterationRuleSource
  from app.infrastructure.transliteration_rules import (
      RulePageParseError,
      UnsupportedLanguage,
      write_cache,
  )

  logger = logging.getLogger(__name__)


  @dataclass(frozen=True)
  class RefreshResult:
      lang: str
      ok: bool
      path: Path | None
      error: str | None


  @dataclass(frozen=True)
  class RefreshRulesUseCase:
      source: TransliterationRuleSource
      rules_dir: Path

      async def execute(self, langs: Sequence[str]) -> list[RefreshResult]:
          logger.info("refreshing rules for langs: %s", list(langs))
          results: list[RefreshResult] = []
          for lang in langs:
              try:
                  ruleset = await self.source.fetch(lang)
                  path = await write_cache(self.rules_dir, ruleset)
                  size = path.stat().st_size
                  logger.info(
                      "parsed %d rule entries for %s, wrote %s (%d bytes)",
                      len(ruleset.entries),
                      lang,
                      path,
                      size,
                  )
                  results.append(RefreshResult(lang=lang, ok=True, path=path, error=None))
              except (UnsupportedLanguage, RulePageParseError) as exc:
                  logger.warning("refresh failed for %s: %s", lang, exc)
                  results.append(RefreshResult(lang=lang, ok=False, path=None, error=str(exc)))
          return results
  ```
  Concern: `RefreshResult` is colocated with the use case (not in `dto.py`) because it's CLI-internal · matches existing convention where `parse_queue_toml` returns CLI-internal types from `run_queued.py` rather than escalating to `dto.py`.
- **MIRROR:** USE_CASE_DATACLASS pattern; LOGGING_PATTERN.
- **IMPORTS:** `TransliterationRuleSource` from ports, `write_cache` + exceptions from infrastructure. The infrastructure → application import is intentional · use cases sometimes need infrastructure-side helpers (cache write) like `TranslateArticleUseCase` doesn't but this is an exception driven by the cache-writer pattern. If concerned, push `write_cache` into a thin port (`RuleCache.write`) · but PRD is explicit about ONE port and treating cache as infra implementation detail.
- **GOTCHA:** swallow `UnsupportedLanguage` and `RulePageParseError` per-lang so `--all` doesn't bail on one bad page. Other exceptions (httpx errors, OSError) propagate · CLI catches them.
- **VALIDATE:** `uv run mypy app/application/use_cases/refresh_rules.py` zero errors.

### Task 6: Wire CLI command
- **ACTION:** Update `app/interfaces/cli/main.py`
- **IMPLEMENT:** add a fourth Typer app and command at the bottom of the file (after `list_drafts_app`):
  ```python
  refresh_rules_app = typer.Typer(add_completion=False, no_args_is_help=True)


  @refresh_rules_app.command()
  def refresh_rules(
      lang: Annotated[
          str | None,
          typer.Option("--lang", help="ISO code of one language to refresh (e.g. 'en')."),
      ] = None,
      all_langs: Annotated[
          bool,
          typer.Option("--all", help="Refresh every supported language."),
      ] = False,
      rules_dir: Annotated[
          Path | None,
          typer.Option(
              "--rules-dir",
              help="Override cache directory (default: ~/.cache/wiki-translator/rules).",
              file_okay=False,
          ),
      ] = None,
  ) -> None:
      """Scrape th.wiki transliteration rule pages and write per-lang JSON cache."""
      from app.infrastructure.transliteration_rules import LANG_TO_TITLE

      if lang is None and not all_langs:
          typer.echo("error: pass --lang <code> or --all", err=True)
          raise typer.Exit(code=2)
      if lang is not None and all_langs:
          typer.echo("error: --lang and --all are mutually exclusive", err=True)
          raise typer.Exit(code=2)
      langs = sorted(LANG_TO_TITLE) if all_langs else [lang]

      try:
          use_case = bootstrap.build_refresh_rules_use_case(rules_dir=rules_dir)
          results = asyncio.run(use_case.execute(langs))
      except Exception as exc:
          typer.echo(f"error: {exc}", err=True)
          _notify_completion("wiki-refresh-rules failed", str(exc))
          raise typer.Exit(code=1) from exc

      ok = sum(1 for r in results if r.ok)
      bad = len(results) - ok
      for r in results:
          status = "ok" if r.ok else "FAIL"
          target = str(r.path) if r.path else r.error or "?"
          typer.echo(f"{status} · {r.lang} · {target}")
      summary = f"{ok} ok · {bad} failed"
      typer.echo(f"done · {summary}")
      _notify_completion("wiki-refresh-rules done", summary)
  ```
- **MIRROR:** CLI_TYPER_APP pattern. Note the `from app.infrastructure...` import is inside the function · matches the existing `from google import genai` lazy-import idiom in `bootstrap.py:67` (avoid heavy imports at module load when CLI is just rendering --help).
- **IMPORTS:** `typer`, `Path` already imported. `Annotated` already imported. `asyncio` already imported.
- **GOTCHA:** `lang is None and not all_langs` is explicit · don't rely on Typer's `no_args_is_help` to handle this because `--rules-dir` alone is a valid invocation that should still error.
- **VALIDATE:** `uv run wiki-refresh-rules --help` prints command help. `uv run wiki-refresh-rules` (no args) prints error and exits non-zero.

### Task 7: Wire bootstrap
- **ACTION:** Update `app/interfaces/cli/bootstrap.py`
- **IMPLEMENT:** add at end of file:
  ```python
  def _resolve_rules_dir(override: Path | None) -> Path:
      if override is not None:
          return override
      env = os.environ.get("WIKI_TRANSLATOR_RULES_DIR")
      if env:
          return Path(env)
      from app.infrastructure.transliteration_rules import default_rules_dir
      return default_rules_dir()


  def build_refresh_rules_use_case(*, rules_dir: Path | None = None) -> RefreshRulesUseCase:
      """Wire `RefreshRulesUseCase` with the live th.wiki adapter."""
      from app.infrastructure.transliteration_rules import (
          WikipediaTransliterationRuleSource,
      )

      user_agent = os.environ.get("WIKI_TRANSLATOR_USER_AGENT", DEFAULT_USER_AGENT)
      return RefreshRulesUseCase(
          source=WikipediaTransliterationRuleSource(user_agent=user_agent),
          rules_dir=_resolve_rules_dir(rules_dir),
      )
  ```
  Top of file gains `from app.application.use_cases.refresh_rules import RefreshRulesUseCase`. Lazy-import the adapter inside the function (mirrors existing genai lazy-import).
- **MIRROR:** BOOTSTRAP_FACTORY pattern.
- **IMPORTS:** `RefreshRulesUseCase` at module top (needed for return annotation under mypy strict).
- **GOTCHA:** mypy strict requires the return-annotation type to be importable at type-check time, so `RefreshRulesUseCase` must be a top-level import. The adapter import stays lazy because BS4/lxml are heavy.
- **VALIDATE:** `uv run mypy app/interfaces/cli/bootstrap.py` zero errors.

### Task 8: Adapter unit tests (network-mocked)
- **ACTION:** Create `tests/infrastructure/test_transliteration_rules.py`
- **IMPLEMENT:** Cover:
  1. `test_satisfies_protocol` · `isinstance(adapter, TransliterationRuleSource)`
  2. `test_fetch_unknown_lang_raises_unsupported` · `await adapter.fetch("xx")` raises `UnsupportedLanguage`
  3. `test_fetch_parses_wikitable_into_entries` · transport returns minimal HTML with one wikitable; assert ≥1 RuleEntry
  4. `test_fetch_handles_multiple_tables` · transport returns HTML with 3 wikitables; assert entries from all 3
  5. `test_fetch_skips_rows_with_missing_cells` · row with only 1 cell ignored
  6. `test_fetch_includes_notes_when_third_cell_present` · 3-cell row → notes populated
  7. `test_fetch_raises_on_zero_entries` · empty wikitable → `RulePageParseError`
  8. `test_fetch_raises_on_5xx` · transport returns 503 → `httpx.HTTPStatusError` propagates
  9. `test_fetch_returns_excerpt_with_first_3_tables_as_markdown` · assert excerpt contains markdown pipes
  10. `test_cache_roundtrip` · `write_cache(...)` then `read_cache(...)` returns equivalent `LanguageRuleSet` (entries tuple comparison ok via dataclass __eq__)
  11. `test_cache_read_missing_returns_none`
  12. `test_cache_read_corrupt_json_returns_none_and_logs_warning`
  13. `test_default_rules_dir_honors_xdg_cache_home`
  14. `@pytest.mark.integration` `test_fetch_against_live_th_wiki_en` · skipif CI, real network, asserts ≥10 entries
- **MIRROR:** MOCK_TRANSPORT_TEST pattern · build a `_make_transport(routes)` helper specific to this file (different shape from the wikipedia_http one because we're returning HTML strings inside the JSON `parse.text` field, not full JSON bodies).
- **IMPORTS:** `httpx`, `pytest`, fixture HTML from `tests/fixtures/transliteration_rules/en.html`.
- **GOTCHA #1:** when mocking the transport, the response body is the JSON envelope `{"parse": {"title": "...", "text": "<HTML>"}}` · the `text` value is the HTML string. Don't put raw HTML at the root of the response.
- **GOTCHA #2:** integration test (#14) needs `@pytest.mark.skipif(os.environ.get("CI") is not None, ...)` matching `test_wikipedia_http.py:197-201`.
- **VALIDATE:** `uv run pytest tests/infrastructure/test_transliteration_rules.py -v` all pass; coverage ≥90% on `app/infrastructure/transliteration_rules.py`.

### Task 9: Use-case unit tests (with fake)
- **ACTION:** Create `tests/fakes/transliteration.py` and `tests/application/test_refresh_rules.py`
- **IMPLEMENT:**
  ```python
  # tests/fakes/transliteration.py
  from __future__ import annotations
  from dataclasses import dataclass, field

  from app.application.dto import LanguageRuleSet
  from app.infrastructure.transliteration_rules import UnsupportedLanguage


  @dataclass
  class FakeTransliterationRuleSource:
      """In-memory `TransliterationRuleSource` for tests · maps lang -> result or exception."""

      results: dict[str, LanguageRuleSet] = field(default_factory=dict)
      raises: dict[str, Exception] = field(default_factory=dict)

      async def fetch(self, lang: str) -> LanguageRuleSet:
          if lang in self.raises:
              raise self.raises[lang]
          if lang not in self.results:
              raise UnsupportedLanguage(f"fake has no result for {lang!r}")
          return self.results[lang]
  ```
  Tests cover:
  1. `test_execute_writes_cache_for_each_lang` · 2 langs, both succeed, 2 cache files exist on disk
  2. `test_execute_swallows_unsupported_language_and_continues` · `--all` with one bad lang; the other still writes
  3. `test_execute_swallows_parse_error_and_continues` · same, but with `RulePageParseError`
  4. `test_execute_propagates_oserror_from_disk` · monkeypatch `write_cache` to raise → propagates up (CLI catches)
  5. `test_execute_returns_results_in_order` · result order matches input lang order
- **MIRROR:** existing fakes in `tests/fakes/translators.py`, `wikipedia.py`, `wikidata.py`. `@dataclass` (not frozen) so tests can populate `results`/`raises` dicts in setup.
- **IMPORTS:** as listed.
- **GOTCHA:** the use case writes to disk · use `tmp_path` pytest fixture for `rules_dir` so tests don't leak files.
- **VALIDATE:** `uv run pytest tests/application/test_refresh_rules.py -v`; `uv run pytest --cov=app/application/use_cases/refresh_rules`.

### Task 10: CLI smoke tests
- **ACTION:** Create `tests/interfaces/cli/test_refresh_rules.py`
- **IMPLEMENT:** Use `typer.testing.CliRunner` with monkeypatched `bootstrap.build_refresh_rules_use_case`. Cover:
  1. `test_missing_args_prints_error_and_exits_2` · `runner.invoke(refresh_rules_app, [])` → exit_code == 2
  2. `test_lang_and_all_mutually_exclusive` · `runner.invoke(refresh_rules_app, ["--lang", "en", "--all"])` → exit_code == 2
  3. `test_lang_invokes_use_case_with_one_lang` · monkeypatched bootstrap returns a fake use case; assert `langs` arg was `["en"]`
  4. `test_all_invokes_use_case_with_sorted_lang_to_title` · assert `langs` was `sorted(LANG_TO_TITLE)`
  5. `test_print_summary_includes_ok_and_fail_counts` · fake use case returns mixed results; assert stdout has `1 ok · 1 failed`
  6. `test_unhandled_exception_exits_1_and_notifies` · monkeypatch bootstrap to raise; exit_code == 1
- **MIRROR:** existing CLI tests at `tests/interfaces/cli/test_translate.py`, `test_translate_queue.py`.
- **IMPORTS:** `typer.testing.CliRunner`, monkeypatching the bootstrap module.
- **GOTCHA:** the autouse `_no_notify` fixture in `tests/conftest.py:13-16` already silences notify-send · don't re-mock.
- **VALIDATE:** `uv run pytest tests/interfaces/cli/test_refresh_rules.py -v`.

### Task 11: Test fixtures
- **ACTION:** Create `tests/fixtures/transliteration_rules/en.html`
- **IMPLEMENT:** A trimmed but realistic copy of one section of the live English rule page. Get it via:
  ```bash
  curl -sL "https://th.wikipedia.org/w/api.php?action=parse&page=วิกิพีเดีย:คู่มือการเขียน/การทับศัพท์ภาษาอังกฤษ&prop=text&format=json&formatversion=2" \
    | python -c 'import json,sys; print(json.load(sys.stdin)["parse"]["text"])' \
    > tests/fixtures/transliteration_rules/en.html.full
  ```
  Then hand-trim to ~100 lines covering 2-3 wikitables for fast tests. Commit only the trimmed version.
- **MIRROR:** existing test convention has no other HTML fixtures · this is the first. Place under `tests/fixtures/<feature>/` as a defensive convention.
- **IMPORTS:** none.
- **GOTCHA:** the live page is large (~150KB). Trim aggressively · tests don't need every grapheme, just enough to validate the parser.
- **VALIDATE:** `wc -l tests/fixtures/transliteration_rules/en.html` < 200.

### Task 12: End-to-end smoke
- **ACTION:** Run the CLI against live th.wiki for English (manual, not automated)
- **IMPLEMENT:**
  ```bash
  uv run wiki-refresh-rules --lang en
  jq '.entries | length' ~/.cache/wiki-translator/rules/en.json
  jq '.entries[:3]' ~/.cache/wiki-translator/rules/en.json
  jq '.excerpt' ~/.cache/wiki-translator/rules/en.json | head -20
  ```
- **MIRROR:** the manual end-to-end smokes documented in PRD verification steps.
- **IMPORTS:** none.
- **GOTCHA #1:** if the live page has changed layout since Task 11's fixture, the parser may produce zero entries → `RulePageParseError`. Recover by re-pulling fixture, adjusting `_parse_rule_html` selectors, re-running tests.
- **GOTCHA #2:** the live page may have ≥50 entries (per PRD success signal). If we get materially fewer, our wikitable detection is dropping rows · investigate before declaring Phase 1 done.
- **VALIDATE:** entries count ≥50, first 3 entries look reasonable (e.g., `{"grapheme": "a", "thai": "เอ", ...}`), excerpt contains markdown pipes and Thai script.

---

## Testing Strategy

### Unit Tests

| Test | Input | Expected Output | Edge Case? |
|---|---|---|---|
| satisfies protocol | adapter constructed | `isinstance(adapter, TransliterationRuleSource)` | no |
| fetch unknown lang | `lang="xx"` | raises `UnsupportedLanguage` | yes (input validation) |
| fetch parses one table | mock HTML with 1 wikitable, 3 rows | LanguageRuleSet with 3 entries | no (happy path) |
| fetch parses multiple tables | mock HTML with 3 wikitables | entries from all 3 in source order | no |
| fetch skips short rows | row with 1 cell | row ignored | yes |
| fetch raises on zero entries | empty wikitable | `RulePageParseError` | yes |
| fetch raises on 5xx | mock 503 response | `httpx.HTTPStatusError` | yes |
| cache write+read roundtrip | write a LanguageRuleSet, read it back | equal entries tuple | no |
| cache read missing | call read_cache for non-existent file | None | yes |
| cache read corrupt JSON | write garbage to <lang>.json | None + warning logged | yes |
| use case writes per lang | 2 supported langs, fake source | 2 cache files on tmp_path | no |
| use case swallows per-lang errors | 1 supported, 1 raises UnsupportedLanguage | 1 cache file written, 1 RefreshResult with error | yes |
| CLI missing args | `wiki-refresh-rules` with no flags | exit code 2, error printed | yes |
| CLI lang + all conflict | `--lang en --all` | exit code 2, error printed | yes |
| CLI happy path | `--lang en` with mocked bootstrap | exit 0, summary printed | no |

### Edge Cases Checklist

- [ ] empty wikitable
- [ ] wikitable with only header row (no data rows)
- [ ] wikitable cell containing nested HTML (e.g., `<sup>`, `<i>`) · `get_text(strip=True)` flattens
- [ ] wikitable with `colspan` / `rowspan` (BS4 `find_all("td")` returns visual cells, not logical · acceptable lossy parse for v1)
- [ ] th.wiki redirect from old title · `redirects=1` param handles
- [ ] LANG_TO_TITLE has langs without rule pages · live test will produce `RulePageParseError`, use case swallows
- [ ] `XDG_CACHE_HOME` set to non-existent dir · `default_rules_dir().mkdir(parents=True, exist_ok=True)` handles in `_write_sync`
- [ ] cache dir not writable · `OSError` propagates up to CLI, exits 1 with the error message
- [ ] concurrent `wiki-refresh-rules --all` invocations · last writer wins · acceptable (manual command, single-user)

---

## Validation Commands

### Static Analysis
```bash
uv run ruff check app tests
uv run ruff format --check app tests
uv run mypy
```
EXPECT: zero errors, zero violations.

### Unit Tests (this phase)
```bash
uv run pytest \
    tests/infrastructure/test_transliteration_rules.py \
    tests/application/test_refresh_rules.py \
    tests/interfaces/cli/test_refresh_rules.py \
    -v
```
EXPECT: all green.

### Coverage check (just the new code)
```bash
uv run pytest \
    --cov=app/application/use_cases/refresh_rules \
    --cov=app/infrastructure/transliteration_rules \
    --cov-report=term-missing \
    --cov-fail-under=90 \
    tests/infrastructure/test_transliteration_rules.py \
    tests/application/test_refresh_rules.py
```
EXPECT: ≥90% on each new module.

### Full Test Suite (no regressions)
```bash
uv run pytest
```
EXPECT: same green-state as before this phase. Existing tests must not regress · the `pyproject.toml` global `--cov-fail-under=80` gate stays in force.

### Pre-commit
```bash
pre-commit run --all-files
```
EXPECT: clean.

### CLI smoke (live th.wiki)
```bash
uv run wiki-refresh-rules --lang en
jq '.entries | length' ~/.cache/wiki-translator/rules/en.json
```
EXPECT: ≥50 entries · matches PRD Phase 1 success signal.

### Integration test (gated)
```bash
uv run pytest -m integration tests/infrastructure/test_transliteration_rules.py
```
EXPECT: passes locally, skipped on CI (env `CI` set).

### Manual Validation
- [ ] `uv run wiki-refresh-rules --help` shows `--lang`, `--all`, `--rules-dir`
- [ ] `uv run wiki-refresh-rules` (no args) prints error and exits non-zero
- [ ] `uv run wiki-refresh-rules --lang en` writes ~/.cache/wiki-translator/rules/en.json with valid JSON
- [ ] `uv run wiki-refresh-rules --all` writes one .json per supported lang, prints `N ok · 0 failed` (or surfaces lang-specific failures)
- [ ] desktop notification fires at end of run (when `notify-send` available)
- [ ] re-running for the same lang overwrites the previous cache atomically (no `.tmp` left behind)

---

## Acceptance Criteria

- [ ] All 12 tasks completed
- [ ] `uv run wiki-refresh-rules --lang en` produces a valid `~/.cache/wiki-translator/rules/en.json` with ≥50 entries
- [ ] `uv run pytest` is green
- [ ] mypy strict + ruff clean
- [ ] Coverage on new modules ≥90%
- [ ] Pre-commit clean

## Completion Checklist

- [ ] Code follows discovered patterns (HTTP_ADAPTER, FILE_IO_ASYNC_WRAP, USE_CASE_DATACLASS, BOOTSTRAP_FACTORY, CLI_TYPER_APP)
- [ ] Error handling matches codebase style (specific exceptions raised; CLI catches and exits non-zero with notification)
- [ ] Logging uses `logging.getLogger(__name__)` + lazy %-formatting
- [ ] Tests follow existing fixture/mock-transport conventions
- [ ] No hardcoded values (env-var fallbacks, default constants at module top)
- [ ] No new architectural patterns invented (this is data-layer plumbing, not abstraction work)
- [ ] Documentation: docstrings on the protocol, the adapter class, and the CLI command body
- [ ] No scope additions: NO validator, NO detector, NO integration into TranslateArticleUseCase, NO review.md changes
- [ ] Self-contained · implementer can complete without re-reading the PRD or asking codebase questions

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| th.wiki rule page layout shifts between fixture-pull and live run | Low | Medium · parser breaks · `RulePageParseError` everywhere | Conservative selector strategy (any `table.wikitable`, ≥2 cells, skip header); fixture comment notes "as-of date"; `--lang en` smoke is the canary |
| BS4 `lxml` parser fallback to `html.parser` if lxml dep missing | Low | Low · slower parse + stricter HTML | Task 0 adds explicit `lxml>=5.3.0` dep; Task 4 GOTCHA #4 calls out the verification |
| `XDG_CACHE_HOME` set to invalid path | Low | Low · `OSError` on first write, surfaces clearly | `_write_sync` calls `mkdir(parents=True, exist_ok=True)`; OSError propagates to CLI |
| Sequential `--all` is too slow on a 20-language pull | Low | Low · seconds-scale | Acceptable; if it ever matters, add `asyncio.gather` later |
| Adding `lxml` adds a heavy native build to the dep tree | Low | Low · pre-built wheels exist for cpython 3.13 on Linux/macOS | uv resolves wheel; `bs4` is the standard for MediaWiki HTML parsing per ecosystem |
| `tempfile.NamedTemporaryFile` on macOS leaves zero-byte tmp files on crash | Very low | Very low · cosmetic, next run overwrites | Acceptable; future task can sweep `*.tmp` on cache read |
| Phase 2's validator port lands with a different DTO shape than Phase 1 publishes | Low | Medium · refactor of `LanguageRuleSet` mid-stream | Phase 1 and 2 both pending → coordinate the DTOs upfront when planning Phase 2; the `excerpt` field is deliberately a free-form string to absorb prompt-format iteration |

## Notes

- **Phase 2 is parallelizable with this work** per PRD line 218 · Phase 2 touches `app/application/services/transliteration_gate.py` and `LiteValidatorAdapter`. No file overlap with Phase 1. If working solo, finish Phase 1 first (the validator is dead weight without rule data).
- **`LANG_TO_TITLE` is a static dict, not a runtime lookup.** Updating it requires re-running Task 1's WebFetch and editing the dict. This is intentional · the parent index page changes rarely, and a runtime fetch adds an extra round-trip + failure mode for no real benefit.
- **The cache JSON shape is the public contract between Phase 1 and Phases 2-3.** Once `<lang>.json` files exist on user disks, `_to_dict` / `_from_dict` shape can only be extended, not broken. Future fields go in with sensible defaults so older caches still deserialize.
- **The `excerpt` field is a Phase 2 input.** It exists in the DTO so Phase 1 can populate it during scrape (cheaper than re-deriving from `entries` later). Phase 2's validator prompt builder will format it further.
- **No integration with `TranslateArticleUseCase` in this phase.** That's Phase 3. The current use case stays untouched.
- **No skill catalog entries to install.** The work uses existing patterns; no new ECC skill is required.
