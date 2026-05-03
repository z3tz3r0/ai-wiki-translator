# ai-wiki-translator

CLI translation drafter for Thai Wikipedia volunteers. Pick a th.wiki article,
the tool fetches the best-language source (auto-picked via Wikidata locale
hints, or English as fallback), translates it section-by-section through
Wikimedia MinT plus Gemini, validates the source against a quality gate, and
writes two review files to disk:

* `<slug>.wikitext` · paste-ready Thai wikitext
* `<slug>.review.md` · source metadata, picked language, gate result, diff
  against the current th.wiki article, and LLM-flagged uncertainties

You read the review notes, paste the wikitext into th.wiki yourself. **The
tool never writes to MediaWiki.**

Out of scope today: web UI, scheduler, Special:Homepage suggestions, OAuth
publishing. The Vite + Solid scaffold under `frontend/` is dormant.

## Requirements

* Python 3.13
* `uv` for project + virtualenv management
* One or more free Gemini API keys from
  [Google AI Studio](https://aistudio.google.com/app/apikey). Multi-key
  rotation is built in · 5 keys gives roughly 75 RPM of free-tier headroom.

No Google Cloud project, no service account, no billing. Term-level machine
translation goes through [Wikimedia MinT](https://translate.wmcloud.org)
which is free and unauthenticated.

## Install

```bash
git clone https://github.com/z3tz3r0/ai-wiki-translator.git
cd ai-wiki-translator
uv sync
```

`uv sync` creates `.venv/` and installs every dependency from `uv.lock`. The
three CLI entry points (`wiki-translate`, `wiki-translate-queue`,
`wiki-list-drafts`) are wired through `[project.scripts]` in `pyproject.toml`
and are runnable as `uv run <cmd>`.

## Configure

Copy the example env file and add your Gemini key(s):

```bash
cp .env.example .env
# edit .env, set GEMINI_API_KEYS=key1,key2,key3
```

The CLI calls `dotenv.load_dotenv()` at startup, so `.env` is picked up
automatically. Shell-exported vars take precedence. See `.env.example` for
optional overrides (model id, sample count for self-consistency, output
directory, custom prompts dir).

## Run

### One article

```bash
uv run wiki-translate "ป๋วย อึ๊งภากรณ์"
```

Optional flags:

| Flag | Purpose |
|---|---|
| `--source-lang LANG` | Skip the auto picker and force a specific source language (`en`, `ja`, `de`, ...) |
| `--glossary PATH` | Apply a `term:translation` glossary file (one entry per line, `:` separator) |
| `--output-dir DIR` | Override the default `~/Documents/wiki-translations/` |

The command prints a one-line summary like

```
passed · puey-ungphakorn · source=en · words=4521 · refs=63
```

and writes the draft files into `<output-dir>/<YYYY-MM-DD>/<slug>/`.

### Queue of articles

Maintain a TOML file with the titles you want to draft:

```toml
# ~/.config/wiki-translator/queue.toml
[[entry]]
title = "ป๋วย อึ๊งภากรณ์"

[[entry]]
title = "ความหลงตนเอง"
source_lang = "en"
glossary = "/abs/path/to/narcissism-terms.txt"
```

Then:

```bash
uv run wiki-translate-queue
# or
uv run wiki-translate-queue --config /custom/path/queue.toml
```

Each entry runs in order. A failure on one article (HTTP error, rate limit
exhaustion, gate rejection) is logged and the next entry continues.

### Review the drafts later

```bash
uv run wiki-list-drafts
uv run wiki-list-drafts --since 2026-05-01
```

Lists drafts on disk, newest first.

## Review-then-paste workflow

1. Run `wiki-translate "<title>"` and wait. Long articles take a few minutes
   even on multi-key rotation.
2. Open `~/Documents/wiki-translations/<date>/<slug>/<slug>.review.md`. Skim:
   * which source language was picked and why
   * quality gate result (`passed` or `rejected_source` with reasons)
   * sections the LLM flagged as uncertain
   * diff vs the current th.wiki article (where overlap exists)
3. Open `<slug>.wikitext`. This is the file you paste.
4. Paste into a `User:<you>/sandbox/<slug>` subpage on th.wiki, render it,
   eyeball formatting and template params. Then move it to article space
   when it looks right.

## Glossary file format

```
Narcissism:ความหลงตนเอง
Sigmund Freud:ซิกมุนด์ ฟรอยด์
ego:อัตตา
```

One entry per line. UTF-8. The English (left) side matches case-insensitively
during the term-replacement pass.

## Project layout

```
app/
  domain/                  pure logic · 100% test coverage
  application/             ports + use cases + services
  infrastructure/          httpx Wikipedia/Wikidata, MinT, Gemini, file IO
  interfaces/
    cli/                   primary surface (Typer)
    http/                  /healthz only · dormant
  prompts/                 system_instruction_th.md, system_instruction_en.md
frontend/                  Vite + Solid scaffold · dormant
tests/                     94% coverage
```

## Development

The full gauntlet matches CI:

```bash
uv run pytest
uv run ruff check
uv run ruff format --check
uv run mypy app tests
pre-commit run --all-files
bun --cwd frontend run build
```

Integration tests that hit live Wikipedia / Wikidata / Gemini / MinT are
gated behind `pytest -m integration` and skipped on CI by default. To run
them locally:

```bash
GEMINI_API_KEY=... uv run pytest -m integration
```

## Architecture notes

Hexagonal · the domain layer is pure, the application layer depends on ports
(Protocols), and infrastructure adapters live behind those ports. Bootstrap
wires the real adapters in `app/interfaces/cli/bootstrap.py`. Tests
substitute fakes from `tests/fakes/` at the same boundary.

Multi-key Gemini rotation: when you set `GEMINI_API_KEYS=k1,k2,k3`,
`GeminiAssistantAdapter` builds one client per key and routes each call
through the least-recently-used key. A 429 on one key fails over to the next.

Self-consistency sampling: each TEXT section is translated N times in
parallel (default 3) and the candidate with best structural fidelity wins
(reference markers preserved, length close to the median). Set
`WIKI_TRANSLATOR_LLM_SAMPLES=1` to disable.

## License

MIT.
