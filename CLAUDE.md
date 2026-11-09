# ai-wiki-translator

Helps a Thai Wikipedia volunteer close the English to Thai gap: Gemini drafts the translation
(the Python CLI in `app/`), Claude plans, assembles and reviews through the skills below, and the
human reviews and publishes. The work exists for public good, so quality and community trust come
before volume.

## Hard rules

- Never write to Wikipedia. No API edits, no bots, never click save. Skills stage the edit in the
  owner's Chrome and the owner presses publish.
- AI translates and copyedits only. No AI-written new article content (วิกิพีเดีย:แบบจำลองภาษาขนาดใหญ่).
- Every published edit names the LLM and credits the English article with its revision id.
- Never revert a revert. Disputes go to the talk page.
- Push to GitHub only when the owner says so in that turn.
- The Gemini model stays on the `gemini-flash-lite-latest` alias unless the owner pins one.

## Skills and agents

| Skill | Does |
|---|---|
| `thwiki-rules` | Shared policy limits, edit-summary formats, AI-signs checklist. Load first |
| `thwiki-translate` | Update or expand an existing Thai article from English, keeping Thai text |
| `thwiki-review` | Mechanical checks, an independent reviewer, a short packet for the owner |
| `thwiki-publish-prep` | Stage the edit and summary in Chrome, talk-page notice, ledger |
| `thai-humanizer` | Vendored Thai style patterns. Use its pattern lists only, never its personality section (NPOV) |

Agents in `.claude/agents/`: `wiki-reviewer` (independent review, never sees how the draft was
made) and `wiki-source-reader` (reads long sources, returns facts with page citations).

MCP servers for this repo (local scope): `chrome-kittipan` (owner's Chrome, CDP 9223, start it
with `cdp-chrome kittipan`), `wikidata` (hosted Wikidata MCP), `code-review-graph`.

## Commands

- Tests: `uv run pytest` (coverage gate 80% on `app/`). Skill scripts are tested in `tests/skills/`.
- Lint and types: `uv run ruff check app tests`, `uv run ruff format --check app tests`, `uv run mypy app tests`
- Translate: `uv run wiki-translate "<Thai title>" --source-lang en` writes to
  `~/Documents/wiki-translations/<date>/<slug>/`
- Skill scripts are stdlib-only: run them with `python -X utf8 -I <script>`.

## Windows notes

- Thai text in `curl.exe` arguments gets mangled by Git Bash. Use the Python scripts, which pass
  Thai titles through intact.
- Run Python with `-X utf8` for Thai output.

<!-- code-review-graph MCP tools -->
## MCP Tools: code-review-graph

**IMPORTANT: This project has a knowledge graph. ALWAYS use the
code-review-graph MCP tools BEFORE using Grep/Glob/Read to explore
the codebase.** The graph is faster, cheaper (fewer tokens), and gives
you structural context (callers, dependents, test coverage) that file
scanning cannot.

### When to use graph tools FIRST

- **Exploring code**: `semantic_search_nodes` or `query_graph` instead of Grep
- **Understanding impact**: `get_impact_radius` instead of manually tracing imports
- **Code review**: `detect_changes` + `get_review_context` instead of reading entire files
- **Finding relationships**: `query_graph` with callers_of/callees_of/imports_of/tests_for
- **Architecture questions**: `get_architecture_overview` + `list_communities`

Fall back to Grep/Glob/Read **only** when the graph doesn't cover what you need.

### Key Tools

| Tool | Use when |
|------|----------|
| `detect_changes` | Reviewing code changes — gives risk-scored analysis |
| `get_review_context` | Need source snippets for review — token-efficient |
| `get_impact_radius` | Understanding blast radius of a change |
| `get_affected_flows` | Finding which execution paths are impacted |
| `query_graph` | Tracing callers, callees, imports, tests, dependencies |
| `semantic_search_nodes` | Finding functions/classes by name or keyword |
| `get_architecture_overview` | Understanding high-level codebase structure |
| `refactor_tool` | Planning renames, finding dead code |

### Workflow

1. The graph auto-updates on file changes (via hooks).
2. Use `detect_changes` for code review.
3. Use `get_affected_flows` to understand impact.
4. Use `query_graph` pattern="tests_for" to check coverage.
