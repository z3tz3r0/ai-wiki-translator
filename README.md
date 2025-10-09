# AI Wiki Translator

Translate English (or other language) Wikipedia articles into Thai using a
modular, open-source friendly toolkit. The project combines deterministic
machine translation for structured content with a large language model that
handles nuanced prose while respecting encyclopaedic style guidelines.

## Features

- **Shared services for CLI & web** – a SOLID-inspired service layer powers
  both the Flask API and command-line interface.
- **Google Cloud Translation + Gemini** – machine translation covers glossary
  terms and markup while Gemini refines long-form paragraphs.
- **Custom glossaries** – supply project-specific terminology via files or the
  web UI.
- **Job orchestration API** – submit work from the browser, poll status, and
  retrieve final wikitext.
- **Token-efficient English prompt** – concise system prompt keeps operating
  costs predictable.

## Project structure

```
app/
  controllers/translation_controller.py   # Flask blueprint (controllers layer)
  services/                               # Translation, prompt, glossary services
  models/                                 # Dataclasses shared across layers
  prompts/system_instruction_en.md        # Default English system prompt
  prompts/system_instruction_th.md        # Thai-language variant of the prompt
  cli.py                                  # Command-line interface
frontend/                                  # Static web client (MVC view layer)
server.py                                  # WSGI entry point (controller bootstrap)
```

## Requirements

- Python 3.10+
- Google Cloud project with the Translation API enabled
- Google AI Studio API key for Gemini 1.5
- Optionally, API keys for other providers (see `.env.example`)

## Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/z3tz3r0/ai-wiki-translator.git
   cd ai-wiki-translator
   ```

2. **Create a virtual environment and install dependencies**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Configure environment variables**

   Copy the example file and fill in the placeholders for the providers you use.
   ```bash
   cp .env.example .env
   ```

   At minimum you need:
   ```bash
   export GOOGLE_CLOUD_PROJECT_ID="your-project"
   export GOOGLE_APPLICATION_CREDENTIALS="/abs/path/service-account.json"
   export GOOGLE_GENAI_API_KEY="your-gemini-key"
    # Optional: choose a different prompt template (English is default)
    export PROMPT_TEMPLATE_PATH="app/prompts/system_instruction_en.md"
   ```

## Usage

### Command-line workflow

Translate any article straight from your shell:

```bash
python -m app.cli "Narcissism" "ความหลงตนเอง" \
  --glossary my_glossary.txt \
  --prompt app/prompts/system_instruction_en.md \
  --output output.txt
```

Arguments:
- `title` – source Wikipedia article title.
- `thai_title` – desired Thai title for the translated page.
- `--glossary` – optional glossary file (defaults to `my_glossary.txt`).
- `--prompt` – alternate system prompt template path.
- `--output` – file path for the translated wikitext (defaults to `output.txt`).

Running `python main.py` continues to invoke the same CLI for backwards
compatibility.

### Web API & frontend

1. Start the Flask server:
   ```bash
   python server.py
   ```

2. Open [http://localhost:5000](http://localhost:5000) (or the port specified
   in the `PORT` environment variable). Submit a job from the UI or interact
   with the endpoints directly:

   | Endpoint | Method | Description |
   | --- | --- | --- |
   | `/api/csrf-token` | GET | Retrieve a CSRF token required for POST requests. |
   | `/api/translate` | POST | Start a translation job. Accepts `title`/`title_name`, `th_title`/`thai_title_name`, optional `glossary` text or `glossary_path`. |
   | `/api/status/<job_id>` | GET | Poll the status (`queued`, `processing`, `completed`, `error`). |
   | `/api/result/<job_id>` | GET | Fetch translated wikitext once the job is complete. |

   Custom glossary text submitted through the UI is sanitised and stored inside
   `.cache/glossaries/<job_id>.txt` for the duration of the job.

## Glossaries & prompts

- `my_glossary.txt` contains curated terms gathered from manual translations.
  Use the `--glossary` option or upload content via the web form to augment it.
- `app/prompts/system_instruction_en.md` is the concise English prompt optimised
  for token usage. `app/prompts/system_instruction_th.md` keeps the guidance in
  Thai for contributors who prefer it. Add further prompt templates next to
  these files.
- Set `PROMPT_TEMPLATE_PATH` in `.env` (or pass `--prompt` to the CLI) to switch
  which template the backend loads by default.

## Testing & development tips

- Run the CLI against a short article to verify credentials before launching
  the web UI.
- The Flask server honours rate limit and concurrent job thresholds through
  environment variables (`RATE_LIMIT`, `MAX_CONCURRENT_JOBS`).
- Temporary glossaries are ignored by Git via `.cache/` in `.gitignore`.

## License

This project is released under the MIT License. Contributions are welcome – fork
the repository, build improvements, and submit a pull request!
