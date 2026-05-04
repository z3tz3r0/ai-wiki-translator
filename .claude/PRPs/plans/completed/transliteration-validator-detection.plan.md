# Plan: Transliteration Validator + Detection Skeleton (Phase 2)

## Codex Brief (read first · this plan will be executed by Codex without ECC tools)

You are implementing **Phase 2** of the transliteration quality gate for `ai-wiki-translator`, a Thai Wikipedia translation drafter (CLI). The repo is on `main` at commit `10fbdc3`. Phase 1 (rule scraper) is already merged. Phase 2 is **parallel-ready** with Phase 1 · zero file overlap, the only Phase 1 artifacts you read are the existing port/DTO surface.

**Hard constraints (project-wide, non-negotiable):**

- **Hexagonal architecture · one-way dependencies:** `domain` → `application` (ports + DTOs + use cases + services) → `infrastructure` (adapters) → `interfaces` (CLI). Lower layers never import upper layers. `application/services/` is pure logic (no IO except via injected ports). `infrastructure/` is where IO lives.
- **Frozen dataclasses for DTOs**, **`runtime_checkable` Protocols for ports**, **async** at every IO boundary. mypy strict mode is enforced.
- **Typography:** No em dashes (`—` U+2014 or `–` U+2013) in code, docstrings, comments, or markdown. Use `·` (middle dot, U+00B7), `:`, commas, parentheses, or restructure. This is a hard project rule and CI does not enforce it · honor it manually.
- **No `print()` in production code · use `logging`. Module-level loggers via `logger = logging.getLogger(__name__)`.**
- **Python 3.13.** Use modern syntax: `X | Y` for unions, `tuple[A, ...]` not `Tuple`, `dict[K, V]` not `Dict`, `from __future__ import annotations` at the top of every module.
- **No bare `except:`. Always except a specific exception class.**
- **ruff lint rules** include `S` (bandit) · no `assert` in production code (asserts in tests are fine, `S101` is ignored).
- **Tests use `pytest-asyncio` with `asyncio_mode = "auto"`** (already configured) · no `@pytest.mark.asyncio` decorator needed.
- **Coverage target: 80% project-wide; aim for ≥95% on the new files.** CI fails below 80%.
- **Output: Unified Diff Patch ONLY. Do not modify files. Claude (the orchestrator) applies the patch.**

**What you can rely on existing in the repo:**

- `app/application/dto.py` already has `RuleEntry`, `LanguageRuleSet` (Phase 1 added these · do NOT redefine them; import from there)
- `app/application/ports.py` already has `TransliterationRuleSource` (Phase 1)
- `app/infrastructure/transliteration_rules.py` already has `WikipediaTransliterationRuleSource`, `read_cache`, `write_cache`, `LANG_TO_TITLE`, `UnsupportedLanguage`, `RulePageParseError`
- `tests/fakes/transliteration.py` already has `FakeTransliterationRuleSource`
- `app/infrastructure/gemini_genai.py` has `GeminiAssistantAdapter` · multi-key, throttle, retry. Phase 2 mirrors its **shape** for the validator adapter but does NOT call into it (different generation config, different output parsing).

---

## Summary

Add a **post-translation transliteration quality gate** with two halves:

1. **Detection** · regex finds candidate Thai-script transliterations of foreign proper nouns in the proposed wikitext (the LLM's output)
2. **Validation** · a batched LLM-judge call sends the candidates + th.wiki rule excerpt to Gemini Flash-Lite, gets back per-candidate verdicts (`approved` / `flagged` / `uncertain`) with rule citations

Phase 2 ships the **skeleton**: ports, DTOs, the orchestrator service, the LiteValidatorAdapter, and unit tests with fakes. Phase 3 (next) wires it into `TranslateArticleUseCase` and the review.md template.

## User Story

As Kittipan reviewing a translated article in `<slug>.review.md`, I want every foreign-name transliteration listed with verdict + rule citation, so I can stop eyeballing and either trust the draft or fix the flagged items.

## Problem → Solution

**Current state:** `TranslateArticleUseCase` produces Thai wikitext where Gemini's transliterations of foreign names ("Anders Hejlsberg" → "แอนเดอส์ เฮลส์เบิร์ก") might or might not follow th.wiki rules, with **no automated check**. The user manually verifies every name before pasting.

**Phase 2 desired state:** A pure-application service `evaluate_transliterations(...)` that, given proposed wikitext + a `LanguageRuleSet` + a `TransliterationValidator`, returns a `TransliterationReport` with per-candidate verdicts. **Not yet wired into the use case** · that is Phase 3.

## Metadata
- **Complexity:** Medium (5-8 new files, ~700 LOC including tests, follows established patterns)
- **Source PRD:** `.claude/PRPs/prds/transliteration-quality-gate.prd.md`
- **PRD Phase:** Phase 2 · Validator + detection skeleton
- **Estimated Files:** 5 created, 2 updated
- **Dependencies on prior phases:** Reads Phase 1's `LanguageRuleSet`, `TransliterationRuleSource`. No code overlap.

---

## UX Design

Internal change · no user-facing UX transformation in Phase 2. Phase 3 surfaces verdicts in `review.md`.

### Interaction Changes
| Touchpoint | Before | After (Phase 2 only) | Notes |
|---|---|---|---|
| `wiki-translate` CLI | runs translation pipeline, writes draft | unchanged | gate not yet wired (Phase 3) |
| `tests/application/` | 7 test files | 8 test files | new: `test_transliteration_gate.py` |
| `tests/infrastructure/` | 8 test files | 9 test files | new: `test_lite_validator.py` |
| `tests/fakes/` | 6 fake modules | 7 fake modules | new: `validator.py` |

---

## Mandatory Reading

Read these IN ORDER before writing code. Snippets are inlined in **Patterns to Mirror** below; the table tells you what each file teaches.

| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `app/application/ports.py` | 1-97 | Existing Protocol shape · mirror for `TransliterationValidator` |
| P0 | `app/application/dto.py` | 1-104 | Existing DTOs · style for `TransliterationCandidate/Verdict/Report` |
| P0 | `app/application/services/diff_summary.py` | 1-49 | Pure-function service shape · mirror for `transliteration_gate.py` |
| P0 | `app/application/services/quality_gate.py` | 1-43 | Validation-result + reasons-tuple pattern |
| P0 | `app/infrastructure/gemini_genai.py` | 1-156 | Multi-key adapter shape · mirror for `LiteValidatorAdapter` |
| P0 | `app/infrastructure/transliteration_rules.py` | 1-140 | Phase 1 adapter · the `LanguageRuleSet` you consume |
| P1 | `tests/application/test_diff_summary.py` | 1-108 | Pure-service test pattern |
| P1 | `tests/infrastructure/test_gemini_genai.py` | 1-100 | LLM adapter test pattern (`SimpleNamespace` fakes for `genai.Client`) |
| P1 | `tests/fakes/transliteration.py` | 1-28 | Fake adapter shape (mutable dataclass with `results`/`raises` dicts) |
| P1 | `tests/application/conftest.py` | 1-34 | The `adapters` fixture (Phase 2 contract style) |
| P2 | `app/prompts/system_instruction_th.md` | 1-27 | Existing prompt-file format · header + numbered rules |

## External Documentation
| Topic | Source | Key Takeaway |
|---|---|---|
| google-genai async API | (already in use in `gemini_genai.py`) | Call shape: `await client.aio.models.generate_content(model=..., contents=..., config=GenerateContentConfig(system_instruction=..., response_mime_type="application/json"))` |
| Thai Unicode block | https://en.wikipedia.org/wiki/Thai_(Unicode_block) | Range `฀-๿` covers all Thai script (consonants, vowels, tone marks, digits) |

---

## Patterns to Mirror

The new code must be indistinguishable from the existing code. Follow these exactly.

### PROTOCOL_DEFINITION
```python
# SOURCE: app/application/ports.py:14-20
@runtime_checkable
class WikipediaReader(Protocol):
    """Read-only access to MediaWiki API across language wikis."""

    async def fetch_article(self, title: str, lang: str) -> Article | None: ...

    async def fetch_langlinks(self, title: str, lang: str) -> dict[str, str]: ...
```

### FROZEN_DTO
```python
# SOURCE: app/application/dto.py:11-19
@dataclass(frozen=True)
class SourceScore:
    """Result of source-language picking · which lang won and why."""

    lang: str
    word_count: int
    ref_count: int
    locale_match: bool
    winning_signal: Literal["locale", "fallback_en", "first_langlink", "override", "error"]
```

### PURE_SERVICE_FUNCTION
```python
# SOURCE: app/application/services/diff_summary.py:10-49
def summarize_diff(
    source_lang: str,
    source_score: SourceScore,
    validation: ValidationResult,
    current_th_wikitext: str,
    proposed_wikitext: str,
) -> ReviewNotes:
    """Wrap metadata + a markdown diff block in a `ReviewNotes` dataclass.

    The diff body is one of:
      * `(new article)` if `current_th_wikitext` is blank/whitespace
      * `(no changes)` if `current_th_wikitext == proposed_wikitext`
      * a fenced ```diff block (unified diff) otherwise
    """
    return ReviewNotes(
        source_lang=source_lang,
        source_score=source_score,
        validation=validation,
        diff_summary=_render_diff(current_th_wikitext, proposed_wikitext),
    )


def _render_diff(current: str, proposed: str) -> str:
    if not current.strip():
        return "(new article)"
    if current == proposed:
        return "(no changes)"
    diff_lines = difflib.unified_diff(...)
```

Note · public function for the orchestrator, private `_helper` for internals. Both module-level free functions, no class wrapper.

### LLM_ADAPTER_DATACLASS
```python
# SOURCE: app/infrastructure/gemini_genai.py:34-51
@dataclass
class GeminiAssistantAdapter:
    """`LLMTranslator` Protocol implementation backed by Google Gemini.

    Construct with one or more ``genai.Client`` instances. Tests typically
    wrap a synthetic client object exposing ``client.aio.models.generate_content``.
    """

    clients: list[Any]
    model: str = "gemini-flash-lite-latest"
    requests_per_minute: int = 12
    max_retries: int = 1
    _last_call_at: list[float] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.clients:
            raise ValueError("`clients` must contain at least one Gemini client")
        self._last_call_at = [0.0] * len(self.clients)
```

Note · **`@dataclass` (mutable)**, NOT `frozen=True`, because the adapter holds throttle state in `_last_call_at`. Tests inject `SimpleNamespace` clients exposing `.aio.models.generate_content`. The validator adapter follows the same shape.

### MULTI_KEY_RETRY_LOOP (full picture)
```python
# SOURCE: app/infrastructure/gemini_genai.py:53-107
async def translate_section(self, content: str, system_instruction: str) -> str:
    sleeps_left = self.max_retries
    failed_in_burst: set[int] = set()
    last_exc: Exception | None = None

    while True:
        key_index = self._pick_freshest_key(exclude=failed_in_burst)

        if key_index is None:
            if sleeps_left <= 0 or last_exc is None:
                break
            attempt = self.max_retries - sleeps_left
            delay = _retry_delay_seconds(last_exc, attempt=attempt)
            ...
            sleeps_left -= 1
            await asyncio.sleep(delay)
            failed_in_burst.clear()
            continue

        await self._throttle(key_index)
        try:
            config = types.GenerateContentConfig(system_instruction=system_instruction)
            response = await self.clients[key_index].aio.models.generate_content(
                model=self.model,
                contents=content,
                config=config,
            )
            self._last_call_at[key_index] = time.monotonic()
            return response.text or ""
        except Exception as exc:
            last_exc = exc
            self._last_call_at[key_index] = time.monotonic()
            if not _is_retriable(exc):
                raise
            failed_in_burst.add(key_index)
```

Reuse this loop verbatim in `LiteValidatorAdapter._call_one()` · only the call config differs (validator wants JSON output).

### FAKE_PORT_DATACLASS
```python
# SOURCE: tests/fakes/transliteration.py:11-28
@dataclass
class FakeTransliterationRuleSource:
    """Maps lang → result or pre-staged exception.

    Mutable (not frozen) so tests can populate ``results``/``raises`` in
    setup. Mirrors the shape of other fakes under ``tests/fakes/``.
    """

    results: dict[str, LanguageRuleSet] = field(default_factory=dict)
    raises: dict[str, Exception] = field(default_factory=dict)

    async def fetch(self, lang: str) -> LanguageRuleSet:
        if lang in self.raises:
            raise self.raises[lang]
        if lang not in self.results:
            raise UnsupportedLanguage(f"fake has no result for {lang!r}")
        return self.results[lang]
```

Mirror this shape for `FakeTransliterationValidator`: mutable dataclass, fields keyed by candidate identity, default behavior + override behavior.

### SERVICE_TEST_PATTERN
```python
# SOURCE: tests/application/test_diff_summary.py:25-58
def test_summarize_diff_returns_review_notes() -> None:
    notes = summarize_diff(
        source_lang="en",
        source_score=_score(),
        validation=_validation_pass(),
        current_th_wikitext="",
        proposed_wikitext="hello",
    )
    assert isinstance(notes, ReviewNotes)
    assert notes.source_lang == "en"
    assert notes.validation.passed is True


def test_summarize_diff_new_article_when_current_blank() -> None:
    notes = summarize_diff(...)
    assert "new article" in notes.diff_summary.lower()
```

Sync `def`, no `@pytest.mark.asyncio` (auto mode). For async tests, just `async def test_foo() -> None:`.

### LLM_ADAPTER_TEST_PATTERN
```python
# SOURCE: tests/infrastructure/test_gemini_genai.py:14-50
def _make_fake_client(
    response_text: str | None = "translated text",
) -> tuple[Any, list[dict[str, Any]]]:
    """Return a `(fake_client, calls)` pair mimicking `genai.Client.aio.models`.

    `calls` records each invocation so tests can assert what was sent.
    """
    calls: list[dict[str, Any]] = []

    async def generate_content(*, model: str, contents: Any, config: Any) -> SimpleNamespace:
        calls.append({"model": model, "contents": contents, "config": config})
        return SimpleNamespace(text=response_text)

    client = SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    )
    return client, calls


def test_satisfies_llm_translator_protocol() -> None:
    client, _ = _make_fake_client()
    adapter = GeminiAssistantAdapter(clients=[client])
    assert isinstance(adapter, LLMTranslator)


async def test_translate_section_returns_response_text() -> None:
    client, _ = _make_fake_client(response_text="แปลแล้ว")
    adapter = GeminiAssistantAdapter(clients=[client])
    out = await adapter.translate_section("source paragraph", "system_instruction")
    assert out == "แปลแล้ว"
```

Mirror exactly for `test_lite_validator.py`. The fake client takes a `response_text` (the LLM's raw JSON string in this case).

### LOGGING_PATTERN
```python
# SOURCE: app/infrastructure/transliteration_rules.py:33
logger = logging.getLogger(__name__)
# ...
logger.info("parsed %d rule entries for %s (title=%r)", len(entries), lang, title)
logger.warning("cache deserialize failed: %s", exc)
```

Always module-level `logger`. Use `%s` / `%r` lazy interpolation, NEVER f-strings inside log calls. Levels: `info` for happy-path milestones, `warning` for soft-degrades, `debug` for verbose detail.

### PROMPT_FILE_FORMAT
```markdown
# SOURCE: app/prompts/system_instruction_th.md:1-7
# ผู้ช่วยแปลวิกิพีเดียภาษาไทย

คุณกำลังแปลส่วนหนึ่งของบทความวิกิพีเดียจาก **ภาษาต้นทางที่ผู้เรียกระบุ**
เป็น **ภาษาไทย** สำหรับเผยแพร่บน th.wikipedia.org ใช้สำนวน คำศัพท์ และ
รูปแบบประโยคแบบเดียวกับบทความที่มีอยู่บน th.wikipedia.org รักษาน้ำเสียง
สารานุกรม ความเป็นกลาง และรูปแบบมาร์กอัปเดิม ปฏิบัติตามกฎต่อไปนี้:
```

Persona heading + numbered rules. Markdown allowed. Loaded as plain text by `FilePromptRepository`. The new `transliteration_judge.md` follows this shape.

---

## Files to Change

| File | Action | Justification |
|---|---|---|
| `app/application/dto.py` | UPDATE (append) | Add 3 frozen DTOs: `TransliterationCandidate`, `TransliterationVerdict`, `TransliterationReport` |
| `app/application/ports.py` | UPDATE (append) | Add `TransliterationValidator` Protocol |
| `app/application/services/transliteration_gate.py` | CREATE | Public `detect_candidates()` + `evaluate_transliterations()` orchestrator |
| `app/infrastructure/lite_validator.py` | CREATE | `LiteValidatorAdapter` · multi-key Gemini call, JSON parse, fallback to uncertain |
| `app/prompts/transliteration_judge.md` | CREATE | System instruction for the LLM judge |
| `tests/fakes/validator.py` | CREATE | `FakeTransliterationValidator` |
| `tests/application/test_transliteration_gate.py` | CREATE | Service-level tests (detection + orchestrator) |
| `tests/infrastructure/test_lite_validator.py` | CREATE | Adapter-level tests (mocked genai client) |
| `tests/application/test_ports.py` | UPDATE | Add `FakeTransliterationValidator` to protocol-satisfaction test |

## NOT Building (defer to Phase 3+)

- **Wiring into `TranslateArticleUseCase.execute()`** · Phase 3 only. Phase 2 leaves the use case untouched.
- **Wiring into `bootstrap.py`** · Phase 3 only. Tests inject the adapter directly via constructor.
- **Updating `_render_review_md()`** · Phase 3 only.
- **`CachedValidatorAdapter` (Gemini 3 Flash Preview + caches.create)** · Phase 5 only.
- **Eval corpus / Wannaphong dict integration** · Phase 4 only.
- **Auto-correction (LLM rewrites flagged items)** · explicitly out of scope per PRD.
- **Per-token verdict splitting** · per Decisions Log line 242, contiguous Thai run = one candidate.

---

## Step-by-Step Tasks

Execute in order. Every task ends with a `VALIDATE` step that must pass before moving on.

### Task 1: Add three DTOs to `app/application/dto.py`

- **ACTION:** Append three frozen dataclasses after the existing `LanguageRuleSet` block (after line 103).
- **IMPLEMENT:**
  ```python
  @dataclass(frozen=True)
  class TransliterationCandidate:
      """One Thai-script transliteration candidate identified by the detector.

      The detector emits these from the proposed wikitext. ``thai`` is the
      contiguous Thai-script span (whitespace allowed); ``context`` is a
      short surrounding wikitext snippet used by the LLM judge to
      disambiguate (e.g. distinguish a place name from a person's name).
      ``latin_hint`` is the Latin-script source name when the detector can
      extract it (e.g. from a wikilink target or a parenthetical disclosure).
      """

      thai: str
      context: str
      latin_hint: str | None = None


  @dataclass(frozen=True)
  class TransliterationVerdict:
      """Per-candidate verdict from a `TransliterationValidator`.

      ``status`` is one of ``approved`` (matches th.wiki rules),
      ``flagged`` (clear rule violation, ``suggested`` should be set to
      the corrected Thai), or ``uncertain`` (validator could not decide,
      e.g. the LLM judge returned malformed JSON or no rule covers this
      grapheme).
      """

      candidate: TransliterationCandidate
      status: Literal["approved", "flagged", "uncertain"]
      rule_citation: str = ""
      suggested: str = ""
      reason: str = ""


  @dataclass(frozen=True)
  class TransliterationReport:
      """Aggregate report from one `evaluate_transliterations` run.

      ``status`` distinguishes a successful gate run (``ok``, even with
      zero candidates) from a soft-degrade (``skipped``, e.g. rules cache
      missing). When ``skipped``, ``skipped_reason`` carries the loud
      banner the user sees in review.md (Phase 3).
      """

      source_lang: str
      candidates_found: int
      verdicts: tuple[TransliterationVerdict, ...]
      status: Literal["ok", "skipped"]
      skipped_reason: str = ""
  ```
- **MIRROR:** FROZEN_DTO. The `Literal[...]` import path is `typing.Literal` (already imported at top of `dto.py`).
- **IMPORTS:** Already in `dto.py`: `from typing import Literal`. Add `from __future__ import annotations` is already present.
- **GOTCHA:** Default values for fields with defaults must come AFTER required fields in the dataclass. The order in the snippet above is correct · `rule_citation`, `suggested`, `reason` all have defaults.
- **VALIDATE:** Run `uv run mypy app/application/dto.py` · expect no errors. The DTOs should be importable: `uv run python -c "from app.application.dto import TransliterationCandidate, TransliterationVerdict, TransliterationReport"`.

### Task 2: Add `TransliterationValidator` Protocol to `app/application/ports.py`

- **ACTION:** Append a new `@runtime_checkable` Protocol after the existing `TransliterationRuleSource` block (after line 96).
- **IMPLEMENT:**
  ```python
  @runtime_checkable
  class TransliterationValidator(Protocol):
      """Judges whether each Thai-script candidate matches th.wiki rules.

      Adapters take a tuple of candidates plus the cached rule set for
      the source language and return one verdict per candidate, in the
      same order. Implementations SHOULD batch all candidates into a
      single call (free-tier compatible) but the contract does not
      enforce this · the orchestrator never inspects call count.

      The verdict tuple length MUST equal ``len(candidates)``. Adapters
      that lose candidates due to LLM truncation or parse failure must
      pad with ``uncertain`` verdicts so order is preserved.
      """

      async def validate(
          self,
          candidates: tuple[TransliterationCandidate, ...],
          rules: LanguageRuleSet,
      ) -> tuple[TransliterationVerdict, ...]: ...
  ```
- **MIRROR:** PROTOCOL_DEFINITION (existing `TransliterationRuleSource`).
- **IMPORTS:** Update the existing import block at the top:
  ```python
  from app.application.dto import (
      DraftMetadata,
      LanguageRuleSet,
      TransliterationCandidate,
      TransliterationVerdict,
  )
  ```
- **GOTCHA:** `runtime_checkable` lets `isinstance(obj, TransliterationValidator)` work in tests, BUT it only checks method names exist · it does NOT check signatures. Tests still need explicit assertion (already the convention in `test_ports.py`).
- **VALIDATE:** `uv run mypy app/application/ports.py`. Then `uv run python -c "from app.application.ports import TransliterationValidator"`.

### Task 3: Implement `transliteration_gate.py` · detection helper + orchestrator

- **ACTION:** Create `app/application/services/transliteration_gate.py` with two public functions: `detect_candidates(wikitext: str) -> tuple[TransliterationCandidate, ...]` and `evaluate_transliterations(...) -> TransliterationReport`.
- **IMPLEMENT:**
  ```python
  """Transliteration quality gate · detect Thai-script candidates and judge them.

  Two responsibilities split into module-level functions:

  * ``detect_candidates(wikitext)`` finds Thai-script spans in the
    proposed wikitext that look like transliterations of foreign proper
    nouns. Conservative regex per PRD risk #5 · over-detect is fine,
    miss is not. Returns deduplicated candidates in source order.
  * ``evaluate_transliterations(...)`` is the orchestrator · runs
    detection, calls the injected validator (one batched call), and
    wraps the result in ``TransliterationReport``. Soft-degrades to
    ``status=skipped`` when ``rules`` is ``None``.

  Pure-application service · no IO except via the injected
  ``TransliterationValidator`` port.
  """

  from __future__ import annotations

  import logging
  import re

  from app.application.dto import (
      LanguageRuleSet,
      TransliterationCandidate,
      TransliterationReport,
      TransliterationVerdict,
  )
  from app.application.ports import TransliterationValidator

  logger = logging.getLogger(__name__)

  # Regex for one Thai-script "word" (contiguous Thai chars).
  _THAI_WORD = r"[฀-๿]+"
  # Multi-word Thai = at least 2 Thai words separated by ASCII spaces.
  # Single-word spans are too noisy · most native Thai is single-word.
  _THAI_RUN_RE = re.compile(rf"{_THAI_WORD}(?:[ \t]+{_THAI_WORD})+")
  # Wikilink with displayed text: [[Latin Target|Thai displayed]]
  _WIKILINK_PIPE_RE = re.compile(
      rf"\[\[(?P<target>[^\]\|]+)\|(?P<displayed>{_THAI_WORD}(?:[ \t]+{_THAI_WORD})+)\]\]"
  )
  # Thai run followed by parenthetical Latin: "แอนเดอส์ เฮลส์เบิร์ก (Anders Hejlsberg)"
  _THAI_THEN_LATIN_PAREN_RE = re.compile(
      rf"(?P<thai>{_THAI_WORD}(?:[ \t]+{_THAI_WORD})+)\s*\((?P<latin>[A-Za-z][A-Za-z .,'\-]+)\)"
  )
  # Internal REF marker, must NOT be treated as a candidate.
  _REF_MARKER_RE = re.compile(r"\[\[REF_\d+\]\]")
  # Surrounding context window for the LLM judge.
  _CONTEXT_RADIUS = 80


  def detect_candidates(wikitext: str) -> tuple[TransliterationCandidate, ...]:
      """Find candidate Thai-script transliterations in ``wikitext``.

      Strategy (conservative, over-detect):

      1. Scan for ``[[target|displayed]]`` wikilinks where ``displayed``
         is a multi-word Thai run · the Latin ``target`` is the hint.
      2. Scan for multi-word Thai runs immediately followed by a
         parenthetical Latin disclosure.
      3. Deduplicate by ``thai`` text · same name appearing twice in
         the article gets one verdict.

      Single-word Thai spans are NOT emitted in v1 · most native Thai
      vocabulary is single-word and false-positive detections train the
      user to ignore the gate. Phase 4 metrics inform whether to widen
      the regex or move to LLM-based detection.
      """
      seen: set[str] = set()
      candidates: list[TransliterationCandidate] = []

      def _emit(thai: str, latin_hint: str | None, span_start: int, span_end: int) -> None:
          if thai in seen:
              return
          seen.add(thai)
          ctx_start = max(0, span_start - _CONTEXT_RADIUS)
          ctx_end = min(len(wikitext), span_end + _CONTEXT_RADIUS)
          context = wikitext[ctx_start:ctx_end]
          candidates.append(
              TransliterationCandidate(
                  thai=thai,
                  context=context,
                  latin_hint=latin_hint,
              )
          )

      for match in _WIKILINK_PIPE_RE.finditer(wikitext):
          displayed = match.group("displayed")
          target = match.group("target").strip()
          # Skip REF markers · they look like wikilinks but are pipeline-internal.
          if _REF_MARKER_RE.fullmatch(match.group(0)):
              continue
          _emit(displayed, target or None, match.start(), match.end())

      for match in _THAI_THEN_LATIN_PAREN_RE.finditer(wikitext):
          thai = match.group("thai")
          latin = match.group("latin").strip()
          _emit(thai, latin or None, match.start(), match.end())

      logger.info("detected %d transliteration candidate(s)", len(candidates))
      return tuple(candidates)


  async def evaluate_transliterations(
      *,
      source_lang: str,
      proposed_wikitext: str,
      rules: LanguageRuleSet | None,
      validator: TransliterationValidator,
  ) -> TransliterationReport:
      """Orchestrate detection + validation, return a structured report.

      Soft-degrades to ``status=skipped`` when ``rules is None`` (the
      Phase 1 cache miss · loud banner per PRD). When candidates are
      found, calls the validator once with all of them and wraps the
      result.
      """
      if rules is None:
          reason = (
              f"no transliteration rules cached for source_lang={source_lang!r} · "
              f"run `wiki-refresh-rules --lang {source_lang}` to enable validation"
          )
          logger.warning("transliteration gate skipped: %s", reason)
          return TransliterationReport(
              source_lang=source_lang,
              candidates_found=0,
              verdicts=(),
              status="skipped",
              skipped_reason=reason,
          )

      candidates = detect_candidates(proposed_wikitext)
      if not candidates:
          logger.info("no transliteration candidates detected · gate trivially passes")
          return TransliterationReport(
              source_lang=source_lang,
              candidates_found=0,
              verdicts=(),
              status="ok",
          )

      verdicts = await validator.validate(candidates, rules)
      if len(verdicts) != len(candidates):
          # Contract violation · pad with uncertain so orchestrator stays
          # crash-free. Adapter SHOULD have padded itself; this is a
          # belt-and-suspenders guard.
          logger.warning(
              "validator returned %d verdicts for %d candidates · padding with uncertain",
              len(verdicts),
              len(candidates),
          )
          padded = list(verdicts)
          for missing in candidates[len(verdicts):]:
              padded.append(
                  TransliterationVerdict(
                      candidate=missing,
                      status="uncertain",
                      reason="validator response truncated",
                  )
              )
          verdicts = tuple(padded)

      logger.info("validator returned %d verdict(s)", len(verdicts))
      return TransliterationReport(
          source_lang=source_lang,
          candidates_found=len(candidates),
          verdicts=verdicts,
          status="ok",
      )
  ```
- **MIRROR:** PURE_SERVICE_FUNCTION (`diff_summary.py`), LOGGING_PATTERN.
- **IMPORTS:** Listed in the snippet.
- **GOTCHA:**
  - The detection regex uses `[฀-๿]` · be careful that the lexer respects the `r""` raw string. `re.compile(rf"...")` is fine because `rf""` keeps backslashes raw and allows f-string substitution.
  - Single-word Thai (length 1 token) is intentionally NOT emitted in v1. Tests must exercise this.
  - The orchestrator is `async def` because `validator.validate` is async, even though `detect_candidates` is sync. Do NOT remove the `async` modifier; Phase 3 awaits this from the use case.
  - Use kw-only args (`*,`) for `evaluate_transliterations` · the existing pattern across the codebase (e.g., `_translate_article` in `translate_article.py:236`).
- **VALIDATE:**
  ```bash
  uv run mypy app/application/services/transliteration_gate.py
  uv run ruff check app/application/services/transliteration_gate.py
  uv run python -c "from app.application.services.transliteration_gate import detect_candidates, evaluate_transliterations"
  ```

### Task 4: Create the LLM-judge prompt template

- **ACTION:** Create `app/prompts/transliteration_judge.md`.
- **IMPLEMENT:**
  ```markdown
  # ผู้ตรวจการทับศัพท์ภาษาไทย

  คุณกำลังตรวจสอบรายการคำทับศัพท์จากภาษาต่างประเทศมาเป็นภาษาไทย
  ที่ปรากฏในร่างบทความวิกิพีเดียภาษาไทย ใช้ **คู่มือการเขียน/การทับศัพท์**
  ของ th.wikipedia.org เป็นมาตรฐานเดียวเท่านั้น ไม่ใช้แหล่งอื่น

  ผู้เรียกจะส่งให้คุณสองสิ่ง:

  1. **ตัดตอนจากหน้ากฎ** (rule excerpt) ของภาษาต้นทาง · ตารางการแมปกราฟีม
     กับคำทับศัพท์ไทยที่ราชบัณฑิตยสถานยอมรับ
  2. **รายการ candidates** · แต่ละชิ้นมี ``thai`` (คำทับศัพท์ที่ใช้
     ในร่าง), ``latin_hint`` (ชื่อต้นฉบับเมื่อพอเดาได้), และ ``context``
     (เนื้อความวิกิรอบ ๆ เพื่อช่วยตัดสิน)

  สำหรับ candidate แต่ละชิ้น ให้ตัดสินสถานะหนึ่งในสามค่า:

  * ``approved`` · ตรงตามตารางในตัดตอน หรือไม่มีกฎที่ขัดแย้งและการสะกด
    ไทยเป็นไปตามแนวที่ปรากฏใน th.wiki ทั่วไป
  * ``flagged`` · ขัดกับตารางในตัดตอนชัดเจน ต้องระบุ ``suggested``
    เป็นคำทับศัพท์ที่ถูกต้อง พร้อม ``rule_citation`` คัดลอกบรรทัดในตัดตอน
  * ``uncertain`` · ตัดสินไม่ได้ (เช่น ต้นฉบับไม่ชัด ตัดตอนไม่ครอบคลุม)

  รูปแบบผลลัพธ์ · JSON array เดียว ไม่มีคำอธิบายอื่น เรียงลำดับตาม
  candidates ที่รับมา:

  ```json
  [
    {
      "thai": "<คำทับศัพท์ของ candidate ชิ้นที่ 1>",
      "status": "approved" | "flagged" | "uncertain",
      "rule_citation": "<บรรทัดจากตัดตอน หรือว่าง>",
      "suggested": "<คำทับศัพท์ที่ถูกต้อง เฉพาะเมื่อ flagged>",
      "reason": "<คำอธิบายสั้น ๆ ภาษาไทย>"
    },
    ...
  ]
  ```

  หาก candidate ชิ้นใดเป็นคำไทยพื้นเมือง (ไม่ใช่ทับศัพท์) ให้ตอบ
  ``approved`` พร้อม ``reason: "คำไทยพื้นเมือง · ไม่อยู่ในขอบเขตการทับศัพท์"``
  ```
- **MIRROR:** PROMPT_FILE_FORMAT (`system_instruction_th.md`).
- **GOTCHA:** This template is **iterated against an eval corpus in Phase 4** per PRD Decisions Log line 245. Phase 2's job is good-enough, not perfect. Don't agonize over wording.
- **VALIDATE:** File exists with non-empty content. No mypy / ruff check applies (markdown).

### Task 5: Implement `LiteValidatorAdapter`

- **ACTION:** Create `app/infrastructure/lite_validator.py`. Mirror `GeminiAssistantAdapter`'s multi-key + retry shape but call `generate_content` with `response_mime_type="application/json"` and parse the JSON response into verdicts.
- **IMPLEMENT:**
  ```python
  """LiteValidatorAdapter · multi-key google-genai client for transliteration judging.

  ``TransliterationValidator`` Protocol implementation. Sends one batched
  call per article (regardless of candidate count) to Gemini Flash-Lite,
  asks for JSON-formatted verdicts, parses them back into typed
  ``TransliterationVerdict`` tuples.

  Mirrors ``GeminiAssistantAdapter``'s multi-key load balancing,
  per-key throttle, and 429/503 retry logic. Differences:

  * Generation config sets ``response_mime_type="application/json"`` so
    the model returns parseable JSON (Gemini honors this in Lite).
  * On parse failure (malformed JSON, length mismatch, missing fields),
    falls back to ``uncertain`` for every candidate · the orchestrator
    treats this as ``ok`` status with degraded verdicts, not a
    ``skipped`` gate run.
  """

  from __future__ import annotations

  import asyncio
  import json
  import logging
  import time
  from dataclasses import dataclass, field
  from typing import Any

  from google.genai import types

  from app.application.dto import (
      LanguageRuleSet,
      TransliterationCandidate,
      TransliterationVerdict,
  )

  logger = logging.getLogger(__name__)

  _STATUS_VALUES: frozenset[str] = frozenset({"approved", "flagged", "uncertain"})


  @dataclass
  class LiteValidatorAdapter:
      """`TransliterationValidator` Protocol implementation backed by Gemini Flash-Lite.

      Construct with one or more ``genai.Client`` instances and the
      system-instruction template (loaded from
      ``app/prompts/transliteration_judge.md``).
      """

      clients: list[Any]
      judge_template: str
      model: str = "gemini-flash-lite-latest"
      requests_per_minute: int = 12
      max_retries: int = 1
      _last_call_at: list[float] = field(default_factory=list, init=False, repr=False)

      def __post_init__(self) -> None:
          if not self.clients:
              raise ValueError("`clients` must contain at least one Gemini client")
          if not self.judge_template.strip():
              raise ValueError("`judge_template` must be non-empty")
          self._last_call_at = [0.0] * len(self.clients)

      async def validate(
          self,
          candidates: tuple[TransliterationCandidate, ...],
          rules: LanguageRuleSet,
      ) -> tuple[TransliterationVerdict, ...]:
          if not candidates:
              return ()
          prompt = _build_user_prompt(candidates, rules)
          raw = await self._generate_json(prompt)
          if raw is None:
              logger.warning(
                  "validator call failed for lang=%s · returning %d uncertain verdicts",
                  rules.lang,
                  len(candidates),
              )
              return _all_uncertain(candidates, "validator call failed")
          verdicts = _parse_verdicts(raw, candidates)
          if verdicts is None:
              logger.warning(
                  "validator JSON parse failed for lang=%s · returning %d uncertain verdicts",
                  rules.lang,
                  len(candidates),
              )
              return _all_uncertain(candidates, "validator response was not parseable JSON")
          return verdicts

      async def _generate_json(self, prompt: str) -> str | None:
          """Multi-key call with retry · returns the LLM's text response or None."""
          sleeps_left = self.max_retries
          failed_in_burst: set[int] = set()
          last_exc: Exception | None = None

          while True:
              key_index = self._pick_freshest_key(exclude=failed_in_burst)
              if key_index is None:
                  if sleeps_left <= 0 or last_exc is None:
                      return None
                  attempt = self.max_retries - sleeps_left
                  delay = _retry_delay_seconds(last_exc, attempt=attempt)
                  logger.warning(
                      "all %d keys exhausted on %s · sleeping %.1fs",
                      len(self.clients),
                      type(last_exc).__name__,
                      delay,
                  )
                  sleeps_left -= 1
                  await asyncio.sleep(delay)
                  failed_in_burst.clear()
                  continue

              await self._throttle(key_index)
              try:
                  config = types.GenerateContentConfig(
                      system_instruction=self.judge_template,
                      response_mime_type="application/json",
                  )
                  response = await self.clients[key_index].aio.models.generate_content(
                      model=self.model,
                      contents=prompt,
                      config=config,
                  )
                  self._last_call_at[key_index] = time.monotonic()
                  return response.text or ""
              except Exception as exc:
                  last_exc = exc
                  self._last_call_at[key_index] = time.monotonic()
                  if not _is_retriable(exc):
                      raise
                  logger.info(
                      "key=%d failed with %s · rotating",
                      key_index,
                      type(exc).__name__,
                  )
                  failed_in_burst.add(key_index)

      def _pick_freshest_key(self, exclude: set[int]) -> int | None:
          candidates = [i for i in range(len(self.clients)) if i not in exclude]
          if not candidates:
              return None
          return min(candidates, key=lambda i: self._last_call_at[i])

      async def _throttle(self, key_index: int) -> None:
          last_at = self._last_call_at[key_index]
          if last_at == 0.0:
              return
          gap = 60.0 / self.requests_per_minute
          elapsed = time.monotonic() - last_at
          if elapsed < gap:
              await asyncio.sleep(gap - elapsed)


  def _build_user_prompt(
      candidates: tuple[TransliterationCandidate, ...],
      rules: LanguageRuleSet,
  ) -> str:
      """Render rule excerpt + candidates as a single user-message payload."""
      payload = {
          "source_lang": rules.lang,
          "rule_excerpt": rules.excerpt,
          "candidates": [
              {
                  "index": i,
                  "thai": c.thai,
                  "latin_hint": c.latin_hint,
                  "context": c.context,
              }
              for i, c in enumerate(candidates)
          ],
      }
      return json.dumps(payload, ensure_ascii=False, indent=2)


  def _parse_verdicts(
      raw: str,
      candidates: tuple[TransliterationCandidate, ...],
  ) -> tuple[TransliterationVerdict, ...] | None:
      """Decode JSON list of verdict objects into typed tuple, or None on failure.

      Returns ``None`` (not all-uncertain) so the caller can distinguish
      "validator gave bad output" from a successful all-uncertain
      response. The caller wraps None into a uniform fallback.
      """
      try:
          data = json.loads(raw)
      except json.JSONDecodeError as exc:
          logger.warning("validator JSON decode failed: %s", exc)
          return None
      if not isinstance(data, list):
          logger.warning("validator JSON was not a list: %s", type(data).__name__)
          return None
      if len(data) != len(candidates):
          logger.warning(
              "validator returned %d items for %d candidates",
              len(data),
              len(candidates),
          )
          return None

      out: list[TransliterationVerdict] = []
      for i, item in enumerate(data):
          if not isinstance(item, dict):
              return None
          status = str(item.get("status", "uncertain"))
          if status not in _STATUS_VALUES:
              status = "uncertain"
          out.append(
              TransliterationVerdict(
                  candidate=candidates[i],
                  status=status,  # type: ignore[arg-type]
                  rule_citation=str(item.get("rule_citation", "")),
                  suggested=str(item.get("suggested", "")),
                  reason=str(item.get("reason", "")),
              )
          )
      return tuple(out)


  def _all_uncertain(
      candidates: tuple[TransliterationCandidate, ...],
      reason: str,
  ) -> tuple[TransliterationVerdict, ...]:
      return tuple(
          TransliterationVerdict(candidate=c, status="uncertain", reason=reason)
          for c in candidates
      )


  def _is_retriable(exc: Exception) -> bool:
      return getattr(exc, "code", None) in (429, 503)


  def _retry_delay_seconds(exc: Exception, attempt: int = 0) -> float:
      if getattr(exc, "code", None) == 503:
          return min(2.0**attempt, 30.0)
      details = getattr(exc, "details", None) or []
      if not isinstance(details, list):
          return 60.0
      for d in details:
          if not isinstance(d, dict):
              continue
          if not str(d.get("@type", "")).endswith("RetryInfo"):
              continue
          raw = d.get("retryDelay", "60s")
          if isinstance(raw, str) and raw.endswith("s"):
              try:
                  return float(raw[:-1])
              except ValueError:
                  pass
      return 60.0
  ```
- **MIRROR:** LLM_ADAPTER_DATACLASS, MULTI_KEY_RETRY_LOOP. The retry helpers (`_is_retriable`, `_retry_delay_seconds`) are duplicated from `gemini_genai.py` rather than imported · keeping the adapter file self-contained mirrors how Phase 1's `transliteration_rules.py` keeps its own helpers. A future refactor (Phase 6 polish) can extract the shared retry logic into a base module.
- **IMPORTS:** Listed in the snippet.
- **GOTCHA:**
  - `# type: ignore[arg-type]` is needed when assigning `str` to a `Literal[...]` field after runtime narrowing · mypy can't track the narrowing through the `if status not in _STATUS_VALUES` check.
  - The retry loop's outer `while True` exit path (`return None` vs `raise`) differs from `gemini_genai.py` · this adapter swallows exhausted retries to a `None` return so the orchestrator can fallback to all-uncertain. `gemini_genai.py` re-raises because translation failures are user-facing.
  - `response.text or ""` not `response.text` · the SDK can return `None` when the model produces no content (rare but documented).
- **VALIDATE:**
  ```bash
  uv run mypy app/infrastructure/lite_validator.py
  uv run ruff check app/infrastructure/lite_validator.py
  uv run python -c "from app.infrastructure.lite_validator import LiteValidatorAdapter"
  ```

### Task 6: Create `FakeTransliterationValidator`

- **ACTION:** Create `tests/fakes/validator.py` with a configurable fake.
- **IMPLEMENT:**
  ```python
  """In-memory `TransliterationValidator` for service + use-case tests."""

  from __future__ import annotations

  from collections.abc import Callable
  from dataclasses import dataclass, field

  from app.application.dto import (
      LanguageRuleSet,
      TransliterationCandidate,
      TransliterationVerdict,
  )


  @dataclass
  class FakeTransliterationValidator:
      """Configurable fake.

      ``verdicts_by_thai`` lets tests pre-stage a verdict per ``thai``
      string. Candidates without an entry get a default ``approved``
      verdict (or one produced by ``default_factory`` when set).
      ``raises`` triggers an exception on the call when set · used to
      verify the orchestrator's error propagation.

      Mutable (not frozen) so tests can populate fields in setup.
      """

      verdicts_by_thai: dict[str, TransliterationVerdict] = field(default_factory=dict)
      default_factory: Callable[[TransliterationCandidate], TransliterationVerdict] | None = None
      raises: Exception | None = None
      calls: list[
          tuple[tuple[TransliterationCandidate, ...], LanguageRuleSet]
      ] = field(default_factory=list)

      async def validate(
          self,
          candidates: tuple[TransliterationCandidate, ...],
          rules: LanguageRuleSet,
      ) -> tuple[TransliterationVerdict, ...]:
          if self.raises is not None:
              raise self.raises
          self.calls.append((candidates, rules))
          out: list[TransliterationVerdict] = []
          for c in candidates:
              if c.thai in self.verdicts_by_thai:
                  out.append(self.verdicts_by_thai[c.thai])
              elif self.default_factory is not None:
                  out.append(self.default_factory(c))
              else:
                  out.append(
                      TransliterationVerdict(
                          candidate=c,
                          status="approved",
                          reason="fake default",
                      )
                  )
          return tuple(out)
  ```
- **MIRROR:** FAKE_PORT_DATACLASS (`tests/fakes/transliteration.py`).
- **IMPORTS:** Listed.
- **GOTCHA:** The `calls` field captures every invocation so tests can assert single-call (batched) semantics. Don't reset it across tests · pytest's function-scoped fixtures already give each test a fresh instance.
- **VALIDATE:**
  ```bash
  uv run mypy tests/fakes/validator.py
  uv run python -c "from tests.fakes.validator import FakeTransliterationValidator; FakeTransliterationValidator()"
  ```

### Task 7: Service tests · `tests/application/test_transliteration_gate.py`

- **ACTION:** Create the test file with both detection tests and orchestrator tests.
- **IMPLEMENT:**
  ```python
  """Tests for `transliteration_gate` · detection regex + orchestrator."""

  from __future__ import annotations

  import datetime

  import pytest

  from app.application.dto import (
      LanguageRuleSet,
      RuleEntry,
      TransliterationCandidate,
      TransliterationVerdict,
  )
  from app.application.services.transliteration_gate import (
      detect_candidates,
      evaluate_transliterations,
  )
  from tests.fakes.validator import FakeTransliterationValidator


  def _ruleset(lang: str = "en") -> LanguageRuleSet:
      return LanguageRuleSet(
          lang=lang,
          title=f"rules-{lang}",
          url=f"https://th.wikipedia.org/wiki/rules-{lang}",
          scraped_at=datetime.datetime(2026, 5, 4, 12, 0, 0),
          entries=(RuleEntry(grapheme="A", thai="เอ"),),
          excerpt="| A | เอ |\n|---|---|",
      )


  # --- detect_candidates ------------------------------------------------------


  def test_detect_finds_thai_inside_wikilink_pipe() -> None:
      wikitext = "[[Anders Hejlsberg|แอนเดอส์ เฮลส์เบิร์ก]] เป็นนักวิทยาศาสตร์"
      out = detect_candidates(wikitext)
      assert len(out) == 1
      assert out[0].thai == "แอนเดอส์ เฮลส์เบิร์ก"
      assert out[0].latin_hint == "Anders Hejlsberg"


  def test_detect_finds_thai_followed_by_latin_paren() -> None:
      wikitext = "ภาษาซีชาร์ป (C Sharp) ถูกออกแบบโดย แอนเดอส์ เฮลส์เบิร์ก (Anders Hejlsberg)"
      out = detect_candidates(wikitext)
      thais = [c.thai for c in out]
      assert "แอนเดอส์ เฮลส์เบิร์ก" in thais
      hint = next(c.latin_hint for c in out if c.thai == "แอนเดอส์ เฮลส์เบิร์ก")
      assert hint == "Anders Hejlsberg"


  def test_detect_skips_single_word_thai() -> None:
      wikitext = "บทความนี้เกี่ยวกับ ภาษา ทั่วไป"
      out = detect_candidates(wikitext)
      assert out == ()


  def test_detect_deduplicates_repeated_candidates() -> None:
      wikitext = (
          "[[Anders Hejlsberg|แอนเดอส์ เฮลส์เบิร์ก]] ทำงาน ... "
          "ต่อมา แอนเดอส์ เฮลส์เบิร์ก (Anders Hejlsberg) ก็ ..."
      )
      out = detect_candidates(wikitext)
      thais = [c.thai for c in out]
      assert thais.count("แอนเดอส์ เฮลส์เบิร์ก") == 1


  def test_detect_skips_ref_markers() -> None:
      wikitext = "[[REF_1]][[REF_2]] [[Anders Hejlsberg|แอนเดอส์ เฮลส์เบิร์ก]]"
      out = detect_candidates(wikitext)
      assert len(out) == 1
      assert out[0].thai == "แอนเดอส์ เฮลส์เบิร์ก"


  def test_detect_returns_tuple() -> None:
      out = detect_candidates("plain text only")
      assert isinstance(out, tuple)
      assert out == ()


  def test_detect_context_window_bounds() -> None:
      wikitext = "x" * 50 + "[[T|แอนเดอส์ เฮลส์เบิร์ก]]" + "y" * 200
      out = detect_candidates(wikitext)
      assert len(out) == 1
      # Context radius is 80 chars · should be much smaller than full wikitext.
      assert len(out[0].context) <= len("[[T|แอนเดอส์ เฮลส์เบิร์ก]]") + 160 + 5


  # --- evaluate_transliterations · happy path ---------------------------------


  async def test_evaluate_returns_skipped_when_rules_none() -> None:
      validator = FakeTransliterationValidator()
      report = await evaluate_transliterations(
          source_lang="en",
          proposed_wikitext="[[X|แอนเดอส์ เฮลส์เบิร์ก]]",
          rules=None,
          validator=validator,
      )
      assert report.status == "skipped"
      assert "wiki-refresh-rules" in report.skipped_reason
      assert report.candidates_found == 0
      assert report.verdicts == ()
      # Validator must not be called when skipped.
      assert validator.calls == []


  async def test_evaluate_returns_ok_zero_when_no_candidates() -> None:
      validator = FakeTransliterationValidator()
      report = await evaluate_transliterations(
          source_lang="en",
          proposed_wikitext="ข้อความไทยล้วน ไม่มีทับศัพท์",
          rules=_ruleset(),
          validator=validator,
      )
      assert report.status == "ok"
      assert report.candidates_found == 0
      assert report.verdicts == ()
      assert validator.calls == []


  async def test_evaluate_calls_validator_once_with_all_candidates() -> None:
      validator = FakeTransliterationValidator()
      wikitext = (
          "[[A|แอนเดอส์ เฮลส์เบิร์ก]] กับ "
          "[[B|มาร์ก ซักเคอร์เบิร์ก]] เป็น ..."
      )
      report = await evaluate_transliterations(
          source_lang="en",
          proposed_wikitext=wikitext,
          rules=_ruleset(),
          validator=validator,
      )
      assert report.status == "ok"
      assert report.candidates_found == 2
      assert len(validator.calls) == 1  # batched
      passed_candidates, passed_rules = validator.calls[0]
      assert len(passed_candidates) == 2
      assert passed_rules.lang == "en"


  async def test_evaluate_preserves_verdict_order() -> None:
      validator = FakeTransliterationValidator(
          verdicts_by_thai={
              "แอนเดอส์ เฮลส์เบิร์ก": TransliterationVerdict(
                  candidate=TransliterationCandidate(
                      thai="แอนเดอส์ เฮลส์เบิร์ก", context=""
                  ),
                  status="approved",
              ),
              "มาร์ก ซักเคอร์เบิร์ก": TransliterationVerdict(
                  candidate=TransliterationCandidate(
                      thai="มาร์ก ซักเคอร์เบิร์ก", context=""
                  ),
                  status="flagged",
                  suggested="มาร์ก ซักเคอร์เบิร์ค",
              ),
          },
      )
      wikitext = (
          "[[A|แอนเดอส์ เฮลส์เบิร์ก]] กับ "
          "[[B|มาร์ก ซักเคอร์เบิร์ก]]"
      )
      report = await evaluate_transliterations(
          source_lang="en",
          proposed_wikitext=wikitext,
          rules=_ruleset(),
          validator=validator,
      )
      thais = [v.candidate.thai for v in report.verdicts]
      assert thais == ["แอนเดอส์ เฮลส์เบิร์ก", "มาร์ก ซักเคอร์เบิร์ก"]


  async def test_evaluate_pads_short_validator_response_with_uncertain() -> None:
      class ShortValidator:
          calls: list[tuple] = []

          async def validate(
              self,
              candidates: tuple[TransliterationCandidate, ...],
              rules: LanguageRuleSet,
          ) -> tuple[TransliterationVerdict, ...]:
              # Return only one verdict for two candidates.
              return (
                  TransliterationVerdict(
                      candidate=candidates[0], status="approved"
                  ),
              )

      validator = ShortValidator()
      wikitext = "[[A|ก ก ก]] กับ [[B|ข ข ข]]"
      # Use a contrived multi-word Thai to exercise the regex; verify padding.
      report = await evaluate_transliterations(
          source_lang="en",
          proposed_wikitext=wikitext,
          rules=_ruleset(),
          validator=validator,
      )
      assert len(report.verdicts) == 2
      assert report.verdicts[0].status == "approved"
      assert report.verdicts[1].status == "uncertain"
      assert "truncated" in report.verdicts[1].reason


  async def test_evaluate_propagates_validator_exception() -> None:
      validator = FakeTransliterationValidator(raises=RuntimeError("boom"))
      with pytest.raises(RuntimeError, match="boom"):
          await evaluate_transliterations(
              source_lang="en",
              proposed_wikitext="[[A|แอนเดอส์ เฮลส์เบิร์ก]]",
              rules=_ruleset(),
              validator=validator,
          )
  ```
- **MIRROR:** SERVICE_TEST_PATTERN (`test_diff_summary.py`), test ordering (helpers → unit → orchestrator).
- **IMPORTS:** Listed.
- **GOTCHA:**
  - `test_detect_skips_single_word_thai` · the wikitext intentionally has space-separated single words; the regex requires 2+ Thai words to form a candidate.
  - `test_evaluate_pads_short_validator_response_with_uncertain` uses contrived Thai single chars (`ก ก ก`) to make the regex match without needing actual transliterations · this exercises the orchestrator's belt-and-suspenders padding code path.
- **VALIDATE:**
  ```bash
  uv run pytest tests/application/test_transliteration_gate.py -v
  uv run mypy tests/application/test_transliteration_gate.py
  ```
  Expect 12 tests, all passing.

### Task 8: Adapter tests · `tests/infrastructure/test_lite_validator.py`

- **ACTION:** Create the test file with `SimpleNamespace`-backed fake genai client mirrors, mirroring `test_gemini_genai.py`.
- **IMPLEMENT:**
  ```python
  """Tests for `LiteValidatorAdapter` · multi-key google-genai validator."""

  from __future__ import annotations

  import datetime
  import json
  from types import SimpleNamespace
  from typing import Any

  import pytest

  from app.application.dto import (
      LanguageRuleSet,
      RuleEntry,
      TransliterationCandidate,
  )
  from app.application.ports import TransliterationValidator
  from app.infrastructure.lite_validator import LiteValidatorAdapter

  _JUDGE_TEMPLATE = "fake judge template"


  def _ruleset() -> LanguageRuleSet:
      return LanguageRuleSet(
          lang="en",
          title="rules-en",
          url="https://th.wikipedia.org/wiki/rules-en",
          scraped_at=datetime.datetime(2026, 5, 4, 12, 0, 0),
          entries=(RuleEntry(grapheme="A", thai="เอ"),),
          excerpt="| A | เอ |",
      )


  def _candidate(thai: str, latin: str | None = None) -> TransliterationCandidate:
      return TransliterationCandidate(thai=thai, context="ctx", latin_hint=latin)


  def _make_fake_client(
      response_text: str | None = "[]",
  ) -> tuple[Any, list[dict[str, Any]]]:
      """Return a `(fake_client, calls)` pair mimicking `genai.Client.aio.models`."""
      calls: list[dict[str, Any]] = []

      async def generate_content(*, model: str, contents: Any, config: Any) -> SimpleNamespace:
          calls.append({"model": model, "contents": contents, "config": config})
          return SimpleNamespace(text=response_text)

      client = SimpleNamespace(
          aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
      )
      return client, calls


  def test_satisfies_protocol() -> None:
      client, _ = _make_fake_client()
      adapter = LiteValidatorAdapter(clients=[client], judge_template=_JUDGE_TEMPLATE)
      assert isinstance(adapter, TransliterationValidator)


  def test_empty_clients_raises() -> None:
      with pytest.raises(ValueError, match="clients"):
          LiteValidatorAdapter(clients=[], judge_template=_JUDGE_TEMPLATE)


  def test_empty_template_raises() -> None:
      client, _ = _make_fake_client()
      with pytest.raises(ValueError, match="judge_template"):
          LiteValidatorAdapter(clients=[client], judge_template="   ")


  async def test_empty_candidates_returns_empty_without_calling_client() -> None:
      client, calls = _make_fake_client()
      adapter = LiteValidatorAdapter(clients=[client], judge_template=_JUDGE_TEMPLATE)
      out = await adapter.validate((), _ruleset())
      assert out == ()
      assert calls == []


  async def test_validate_parses_well_formed_json() -> None:
      payload = json.dumps(
          [
              {
                  "thai": "แอนเดอส์ เฮลส์เบิร์ก",
                  "status": "approved",
                  "rule_citation": "rule line",
                  "suggested": "",
                  "reason": "matches",
              }
          ],
          ensure_ascii=False,
      )
      client, _ = _make_fake_client(response_text=payload)
      adapter = LiteValidatorAdapter(clients=[client], judge_template=_JUDGE_TEMPLATE)
      out = await adapter.validate(
          (_candidate("แอนเดอส์ เฮลส์เบิร์ก", "Anders Hejlsberg"),),
          _ruleset(),
      )
      assert len(out) == 1
      assert out[0].status == "approved"
      assert out[0].rule_citation == "rule line"
      assert out[0].candidate.thai == "แอนเดอส์ เฮลส์เบิร์ก"


  async def test_validate_falls_back_to_uncertain_on_malformed_json() -> None:
      client, _ = _make_fake_client(response_text="not json")
      adapter = LiteValidatorAdapter(clients=[client], judge_template=_JUDGE_TEMPLATE)
      out = await adapter.validate((_candidate("แอนเดอส์ เฮลส์เบิร์ก"),), _ruleset())
      assert len(out) == 1
      assert out[0].status == "uncertain"
      assert "parseable JSON" in out[0].reason


  async def test_validate_falls_back_when_response_length_mismatch() -> None:
      payload = json.dumps([{"thai": "x", "status": "approved"}])  # 1 item for 2 candidates
      client, _ = _make_fake_client(response_text=payload)
      adapter = LiteValidatorAdapter(clients=[client], judge_template=_JUDGE_TEMPLATE)
      out = await adapter.validate(
          (_candidate("ก ก ก"), _candidate("ข ข ข")),
          _ruleset(),
      )
      assert len(out) == 2
      assert all(v.status == "uncertain" for v in out)


  async def test_validate_coerces_unknown_status_to_uncertain() -> None:
      payload = json.dumps([{"status": "totally_invalid", "reason": "x"}])
      client, _ = _make_fake_client(response_text=payload)
      adapter = LiteValidatorAdapter(clients=[client], judge_template=_JUDGE_TEMPLATE)
      out = await adapter.validate((_candidate("แอนเดอส์ เฮลส์เบิร์ก"),), _ruleset())
      assert out[0].status == "uncertain"


  async def test_validate_passes_judge_template_as_system_instruction() -> None:
      payload = json.dumps([{"status": "approved"}])
      client, calls = _make_fake_client(response_text=payload)
      adapter = LiteValidatorAdapter(clients=[client], judge_template="my judge")
      await adapter.validate((_candidate("แอนเดอส์ เฮลส์เบิร์ก"),), _ruleset())
      assert len(calls) == 1
      assert calls[0]["config"].system_instruction == "my judge"


  async def test_validate_requests_json_mime_type() -> None:
      payload = json.dumps([{"status": "approved"}])
      client, calls = _make_fake_client(response_text=payload)
      adapter = LiteValidatorAdapter(clients=[client], judge_template=_JUDGE_TEMPLATE)
      await adapter.validate((_candidate("แอนเดอส์ เฮลส์เบิร์ก"),), _ruleset())
      assert calls[0]["config"].response_mime_type == "application/json"


  async def test_validate_uses_configured_model() -> None:
      payload = json.dumps([{"status": "approved"}])
      client, calls = _make_fake_client(response_text=payload)
      adapter = LiteValidatorAdapter(
          clients=[client],
          judge_template=_JUDGE_TEMPLATE,
          model="custom-model",
      )
      await adapter.validate((_candidate("แอนเดอส์ เฮลส์เบิร์ก"),), _ruleset())
      assert calls[0]["model"] == "custom-model"


  async def test_validate_load_balances_across_keys() -> None:
      """Two clients · second call must hit the freshest (least-recently-used) key."""
      payload = json.dumps([{"status": "approved"}])

      def make_marked_client(label: str) -> tuple[Any, list[str]]:
          hits: list[str] = []

          async def generate_content(*, model: str, contents: Any, config: Any) -> SimpleNamespace:
              hits.append(label)
              return SimpleNamespace(text=payload)

          return (
              SimpleNamespace(
                  aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
              ),
              hits,
          )

      c1, hits1 = make_marked_client("k1")
      c2, hits2 = make_marked_client("k2")
      adapter = LiteValidatorAdapter(clients=[c1, c2], judge_template=_JUDGE_TEMPLATE)

      cand = (_candidate("แอนเดอส์ เฮลส์เบิร์ก"),)
      await adapter.validate(cand, _ruleset())
      await adapter.validate(cand, _ruleset())

      assert len(hits1) == 1
      assert len(hits2) == 1


  async def test_validate_429_falls_back_to_uncertain() -> None:
      class RateLimit(Exception):
          code = 429
          details = [{"@type": "google.rpc.RetryInfo", "retryDelay": "0s"}]

      async def always_429(*, model: str, contents: Any, config: Any) -> SimpleNamespace:
          raise RateLimit("rate limited")

      client = SimpleNamespace(
          aio=SimpleNamespace(models=SimpleNamespace(generate_content=always_429))
      )
      adapter = LiteValidatorAdapter(
          clients=[client],
          judge_template=_JUDGE_TEMPLATE,
          max_retries=1,
      )
      out = await adapter.validate((_candidate("แอนเดอส์ เฮลส์เบิร์ก"),), _ruleset())
      # All 429s exhausted · adapter falls back to all-uncertain (not raise).
      assert len(out) == 1
      assert out[0].status == "uncertain"
      assert "validator call failed" in out[0].reason


  async def test_validate_non_retriable_exception_propagates() -> None:
      async def boom(*, model: str, contents: Any, config: Any) -> SimpleNamespace:
          raise RuntimeError("something else")

      client = SimpleNamespace(
          aio=SimpleNamespace(models=SimpleNamespace(generate_content=boom))
      )
      adapter = LiteValidatorAdapter(clients=[client], judge_template=_JUDGE_TEMPLATE)
      with pytest.raises(RuntimeError, match="something else"):
          await adapter.validate((_candidate("แอนเดอส์ เฮลส์เบิร์ก"),), _ruleset())
  ```
- **MIRROR:** LLM_ADAPTER_TEST_PATTERN (`test_gemini_genai.py`).
- **IMPORTS:** Listed.
- **GOTCHA:**
  - The 429 test uses `retryDelay: "0s"` so the test doesn't actually sleep. With `max_retries=1`, the adapter sleeps once (0s), retries (still fails), gives up, returns all-uncertain.
  - `test_validate_passes_judge_template_as_system_instruction` accesses `calls[0]["config"].system_instruction` · this works because `types.GenerateContentConfig` is a Pydantic model and the kwarg becomes an attribute.
  - For the multi-key test, both `await adapter.validate(...)` calls must happen synchronously (no `asyncio.gather`) so the LRU pick-freshest logic is deterministic.
- **VALIDATE:**
  ```bash
  uv run pytest tests/infrastructure/test_lite_validator.py -v
  uv run mypy tests/infrastructure/test_lite_validator.py
  ```
  Expect ~14 tests, all passing.

### Task 9: Update `tests/application/test_ports.py` for protocol satisfaction

- **ACTION:** Add a single import + assertion to the existing `test_fakes_satisfy_protocols` function (around line 162). The new fake must structurally satisfy the new Protocol.
- **IMPLEMENT:**

  Add to imports:
  ```python
  from app.application.ports import TransliterationValidator
  from tests.fakes.validator import FakeTransliterationValidator
  ```

  Add inside `test_fakes_satisfy_protocols`:
  ```python
  assert isinstance(FakeTransliterationValidator(), TransliterationValidator)
  ```
- **MIRROR:** Existing `test_fakes_satisfy_protocols` body · one `isinstance` assert per fake.
- **GOTCHA:** Don't replace the function body wholesale; keep all existing asserts. Just add one line and one import.
- **VALIDATE:**
  ```bash
  uv run pytest tests/application/test_ports.py -v
  ```
  Expect all existing tests + the protocol-satisfaction one still passing.

### Task 10: Run the full validation gauntlet

- **ACTION:** Run every check the CI runs. Fix until all green.
- **IMPLEMENT:**
  ```bash
  uv run ruff check
  uv run ruff format --check
  uv run mypy
  uv run pytest
  ```
- **GOTCHA:**
  - If `ruff format --check` fails, run `uv run ruff format` to fix and re-check.
  - If coverage drops below 80%, the new files probably have an uncovered branch · review `tests/application/test_transliteration_gate.py` and `tests/infrastructure/test_lite_validator.py` for missing edge cases.
  - The pre-commit hook config (`.pre-commit-config.yaml`) runs the same checks · if you have `pre-commit` installed locally, `pre-commit run --all-files` is a faster lap.
- **VALIDATE:** All four commands return exit 0.

---

## Testing Strategy

### Unit Tests

| Test | Input | Expected Output | Edge Case? |
|---|---|---|---|
| `detect_finds_thai_inside_wikilink_pipe` | `[[Anders Hejlsberg|แอนเดอส์ เฮลส์เบิร์ก]] เป็น...` | 1 candidate, latin_hint="Anders Hejlsberg" | no |
| `detect_finds_thai_followed_by_latin_paren` | `แอนเดอส์ เฮลส์เบิร์ก (Anders Hejlsberg)` | 1 candidate with hint | no |
| `detect_skips_single_word_thai` | `บทความ ภาษา` | empty tuple | yes |
| `detect_deduplicates_repeated` | same Thai twice | 1 candidate | yes |
| `detect_skips_ref_markers` | `[[REF_1]] [[REF_2]]` | empty | yes |
| `detect_returns_tuple` | plain text | `()` | yes |
| `detect_context_window_bounds` | very long wikitext | context ≤ ~165 chars | yes |
| `evaluate_returns_skipped_when_rules_none` | rules=None | status=skipped | yes |
| `evaluate_returns_ok_zero_when_no_candidates` | Thai-only wikitext | status=ok, candidates=0 | yes |
| `evaluate_calls_validator_once_with_all_candidates` | 2 candidates | 1 call, 2 candidates passed | yes |
| `evaluate_preserves_verdict_order` | mixed verdicts | order matches detection order | no |
| `evaluate_pads_short_validator_response_with_uncertain` | adapter returns 1 for 2 | uncertain padding | yes |
| `evaluate_propagates_validator_exception` | adapter raises | exception propagates | yes |
| `lite_validate_satisfies_protocol` | new adapter | isinstance(TransliterationValidator) | no |
| `lite_validate_empty_clients_raises` | clients=[] | ValueError | yes |
| `lite_validate_empty_template_raises` | template=" " | ValueError | yes |
| `lite_validate_empty_candidates_short_circuit` | candidates=() | empty tuple, 0 LLM calls | yes |
| `lite_validate_parses_well_formed_json` | valid JSON | parsed verdicts | no |
| `lite_validate_falls_back_to_uncertain_on_malformed_json` | "not json" | all uncertain | yes |
| `lite_validate_falls_back_when_response_length_mismatch` | 1 result for 2 cands | all uncertain | yes |
| `lite_validate_coerces_unknown_status_to_uncertain` | status="bogus" | uncertain | yes |
| `lite_validate_passes_judge_template_as_system_instruction` | template="my judge" | sent in config | no |
| `lite_validate_requests_json_mime_type` | any call | response_mime_type="application/json" | no |
| `lite_validate_uses_configured_model` | model="custom" | model passed through | no |
| `lite_validate_load_balances_across_keys` | 2 keys, 2 calls | each key hit once | no |
| `lite_validate_429_falls_back_to_uncertain` | always 429 | all uncertain | yes |
| `lite_validate_non_retriable_propagates` | RuntimeError | re-raised | yes |
| `test_fakes_satisfy_protocols` updated | new fake | isinstance OK | no |

Total: 25+ test cases.

### Edge Cases Checklist
- [x] Empty input (empty wikitext, empty candidates list)
- [x] Thai-only wikitext (no foreign hints)
- [x] Multiple candidates batched in one call
- [x] REF markers excluded from detection
- [x] Duplicate candidates deduplicated
- [x] LLM JSON parse failure → all uncertain
- [x] LLM length mismatch → all uncertain
- [x] LLM unknown status → uncertain
- [x] 429 retry exhaustion → all uncertain
- [x] Non-retriable exception → propagates
- [x] Multi-key LRU load balancing

---

## Validation Commands

### Static Analysis
```bash
uv run mypy
```
EXPECT: Zero errors.

```bash
uv run ruff check
uv run ruff format --check
```
EXPECT: No lint findings, no format diffs.

### Unit Tests · new files only
```bash
uv run pytest tests/application/test_transliteration_gate.py tests/infrastructure/test_lite_validator.py tests/application/test_ports.py -v
```
EXPECT: ~25 new test cases pass + existing test_ports.py pass.

### Full Test Suite
```bash
uv run pytest
```
EXPECT: All tests pass, coverage ≥80% project-wide.

### Coverage on New Files
```bash
uv run pytest --cov=app/application/services/transliteration_gate --cov=app/infrastructure/lite_validator --cov-report=term-missing
```
EXPECT: ≥95% line coverage on the two new modules.

### Manual Validation
- [ ] `uv run python -c "from app.application.dto import TransliterationCandidate, TransliterationVerdict, TransliterationReport; from app.application.ports import TransliterationValidator; from app.application.services.transliteration_gate import detect_candidates, evaluate_transliterations; from app.infrastructure.lite_validator import LiteValidatorAdapter; print('imports ok')"` prints `imports ok`.
- [ ] No new `print()` calls introduced anywhere.
- [ ] No em dashes anywhere in the diff.

---

## Acceptance Criteria
- [ ] All 10 tasks completed.
- [ ] All validation commands pass (mypy, ruff check + format check, pytest, coverage).
- [ ] ~25 new tests written and passing.
- [ ] Project coverage ≥80%; new-file coverage ≥95%.
- [ ] No type errors, no lint errors.
- [ ] No use case / bootstrap modifications (those are Phase 3).

## Completion Checklist
- [ ] Code follows hexagonal layering · `services/` is pure, `infrastructure/` does IO only.
- [ ] Frozen dataclasses for all 3 new DTOs.
- [ ] `runtime_checkable` Protocol for `TransliterationValidator`.
- [ ] Logging follows `logger = logging.getLogger(__name__)` + lazy %-format pattern.
- [ ] Tests follow AAA structure and use module-level helper functions for fixtures.
- [ ] No hardcoded secrets, no env-var reads in application/services layer.
- [ ] No `print()` statements anywhere in `app/`.
- [ ] No em dashes in any modified file.
- [ ] `__future__ annotations` import at top of every new module.

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Detection regex catches false positives (single multi-word native Thai phrase mistaken for transliteration) | Medium | LLM judge labels as approved with reason "native Thai" | Phase 4 metrics measure FP rate; iterate regex if needed |
| LLM returns malformed JSON in production | Medium | All-uncertain verdicts shown to user | Adapter already falls back · acceptable degradation |
| Adapter retry loop ends on `return None` differs from `gemini_genai.py`'s re-raise | Low | Behavior split between two adapters | Documented in adapter docstring |
| Coverage gap on retry loop (timing-sensitive) | Medium | CI flake | The 429 test uses `retryDelay: "0s"` to keep timing deterministic |
| `Literal["approved", "flagged", "uncertain"]` mypy narrowing requires `# type: ignore` | Low | Tech-debt comment | Documented in adapter |

## Notes

- **Why this Phase 2 doesn't touch bootstrap.py:** Phase 3 wires the adapter; Phase 2's job is to make it constructible and unit-tested in isolation. Tests inject the adapter via constructor; the use case doesn't see it yet.
- **Why the LiteValidatorAdapter doesn't reuse `GeminiAssistantAdapter`:** They differ in three ways · (1) generation config (`response_mime_type="application/json"` for validator), (2) failure semantics (validator falls back to uncertain, translator re-raises), (3) public method signature (`validate(...) -> tuple[Verdict]` vs `translate_section(content, sys) -> str`). A shared base class would buy minimal LOC savings and force premature abstraction. Phase 6 polish can extract a `_BaseGeminiAdapter` if a third adapter materializes.
- **Phase 3 hand-off:** Phase 3 reads the cache via `read_cache(rules_dir, source_lang)` (Phase 1's helper), passes the result + adapter into `evaluate_transliterations(...)`, slots the call between section translation and `save_draft` in `TranslateArticleUseCase.execute()` (around line 191-192), and renders the report into review.md.
- **Codex reminder:** Output must be a Unified Diff Patch with hunks for every file change. No actual file mutations. The orchestrator (Claude in the parent session) applies the patch.
