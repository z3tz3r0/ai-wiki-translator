# Transliteration Quality Gate

## Problem Statement

`wiki-translate` produces Thai-script transliterations of foreign proper nouns (e.g. "Anders Hejlsberg" → "แอนเดอส์ เฮลส์เบิร์ก") that frequently don't follow th.wiki community style or ราชบัณฑิตยสถาน rules. The current quality gate checks source-side metrics only · word count, ref count, required sections · so transliteration errors slip silently into drafts. The cost: every draft requires the user to manually verify each foreign name against the rule pages before pasting to th.wiki, defeating the time savings the CLI is supposed to provide.

## Evidence

- User direct quote: "the transliteration might not accurate and I wants precise and spot on accuracy transliteration"
- User direct quote: "the system prompt do too much thing" · diagnosed root cause: prompt overload diluting transliteration enforcement
- User direct quote: "translation accuracy is one of the core feature, transliteration is one of them. it's better to get it right now."
- Codebase analysis: `app/prompts/system_instruction_th.md` line 15 says "ทับศัพท์ไทยที่เป็นที่ยอมรับ" but with no rule pointer · Gemini has no enforcement mechanism
- Codebase analysis: `app/application/services/quality_gate.py:20` runs source-side only, never validates Thai output
- Real-use evidence: ภาษาซีชาร์ป translation (2026-05-04, 242 sections, 51 min) produced ~30+ proper-noun transliterations with no automated validation; user manually verified each before paste

## Proposed Solution

Add a post-translation **transliteration quality gate** as a new step in `TranslateArticleUseCase.execute()`, slotted between section translation and `save_draft`. The gate runs an LLM-as-judge validator with **th.wiki rule pages as the source of truth**, scraped once via a separate `wiki-refresh-rules` CLI command and cached as per-language JSON. Detection finds candidate transliterations in the proposed wikitext via regex; the validator batches all candidates into one Gemini Flash-Lite call (free-tier-compatible, no cache), receiving the relevant rule excerpt as context and returning verdicts (approved / flagged with rule citation / suggested correction). Verdicts are written to `<slug>.review.md` so the user can read flagged items, fix them in the wikitext, and paste with confidence. Hexagonal: new ports `TransliterationRuleSource` and `TransliterationValidator`, the validator with two adapters · Lite default (ships v1) and Cached opt-in (Phase 5). Source of truth is th.wiki rules, not Wunsen / wannaphong / Royal Society publications · Thai-Wikipedia-first per user direction.

## Key Hypothesis

We believe a **post-translation gate that cites th.wiki rule excerpts for each flagged transliteration** will let Kittipan **trust un-flagged transliterations and fix flagged ones without proofreading from scratch** for the wiki-translate CLI workflow.

We'll know we're right when, on an eval corpus seeded by the Wannaphong dict and grown with hand-labeled cases from real drafts, the gate's **false positive rate stays under 10%** (the primary trust-keeping metric · a noisy gate trains the user to dismiss warnings) and **recall is ≥75%** of actual errors flagged with correct rule citations. Per the 2026-05-04 council, FP rate is the priority over recall · a quiet 75%-recall gate beats a noisy 85%-recall gate every time.

## What We're NOT Building

- **Auto-correction in v1** · gate flags, human fixes. Auto-rewrite would silently corrupt drafts when the verdict itself is wrong. Defer until v1 verdict accuracy is proven.
- **Real-time scraping per translation** · rule pages change rarely. `wiki-refresh-rules` is a separate manual command, not auto.
- **Generic Thai grammar / style checking** · this gate is transliteration-specific. Politeness register, idiom checks, factual accuracy are out.
- **Reverse-direction translation (Thai → English)** · CLI stays one-way.
- **Rule sources beyond th.wiki** · Royal Society publications direct, ICU, Wunsen, wannaphong dict are NOT canonical. th.wiki is the only source of truth in v1. Wunsen / dict become eval-time fixtures only, never authority.
- **Per-section validation** · gate runs once per article, not per section. Mirrors `summarize_diff` (article-level service).
- **LangChain wholesale adoption** · stick with google-genai SDK; existing port abstraction handles provider portability if ever needed.

## Success Metrics

| Metric | Priority | Target | How Measured |
|--------|----------|--------|--------------|
| **False positive rate** | **PRIMARY** | <10% of correct transliterations falsely flagged | Eval corpus (Wannaphong dict + hand-labeled additions); count flagged-but-correct |
| Recall on eval corpus | Secondary | ≥75% of actual errors flagged | Same corpus; count missed-by-gate / actual-errors |
| User trust delta | Outcome | "I read review.md and trust it" (subjective, self-reported) | After 5+ real drafts use the gate, ask: "Do you skip eyeballing un-flagged transliterations?" · binary yes/no |
| Latency overhead per draft | Guardrail | <2 minutes added to translation runtime | Compare end-to-end timing of translate-only vs translate+gate on same article |
| Free-tier quota survival | Guardrail | Gate runs without 429-storm or quota exhaustion on a 250-section article | Run gate on ภาษาซีชาร์ป-class article, confirm no aborts |

> **Why FP-first:** per 2026-05-04 council (Skeptic + Pragmatist + Critic convergent insight), a gate that flags 30% of correct transliterations trains the user to dismiss warnings, defeating the whole purpose. FP rate is the trust-keeping metric. Recall is secondary because the human still reviews the draft · a missed flag costs eyeball time, a false flag costs trust.

## Open Questions

Resolved by 2026-05-04 council are listed in the Decisions Log. Remaining open items are build-time iterations, not v1 blockers:

- [ ] **Batched call prompt template.** Exact phrasing of the LLM-judge prompt (system instruction split, output schema · JSON vs plaintext, citation format). Pin during Phase 2 by iterating against the eval corpus seeded from Wannaphong.
- [ ] **Parent rule-index page structure.** `WebFetch` the th.wiki parent (`หลักเกณฑ์การทับศัพท์ของราชบัณฑิตยสถานและสำนักงานราชบัณฑิตยสภา`) at Phase 1 build time, enumerate child links from the wikitable. Resolved at Phase 1 start.
- [ ] **Free-tier RPM/TPM for Gemini 3 Flash Preview.** Unknown until measured. Resolved at Phase 5 start (look up at ai.google.dev/gemini-api/docs/rate-limits and confirm with one test call). Not v1-blocking.

---

## Users & Context

**Primary User**

- **Who**: Kittipan.w (single user · Thai Wikipedia volunteer translator). User account on th.wiki linked to the Special:Homepage suggested-edits queue.
- **Current behavior**: Picks suggested-edit titles from Special:Homepage, runs `wiki-translate "<title>"`, waits 30-60 minutes for the draft, opens `<slug>.review.md`, manually verifies every foreign-name transliteration by Googling th.wiki rule pages or searching past articles, fixes errors in the wikitext, pastes to a User: subpage to render and verify, moves to article space.
- **Trigger**: Wants to draft a real article. Picks one with foreign proper nouns (most do). Cannot trust the LLM's transliteration without manual verification.
- **Success state**: Reads review.md, sees flagged transliterations with rule citations, fixes those few, pastes the rest unchanged, total review time <5 minutes per draft.

**Job to Be Done**

When I read `<slug>.review.md` before pasting to th.wiki, I want every foreign-name transliteration to be either rule-approved or flagged with the relevant rule excerpt, so I can stop eyeballing and either trust the draft or fix the flagged items.

**Non-Users**

- Bot operators doing mass translation · this CLI is one-at-a-time
- Translators going Thai → other languages · CLI direction is one-way
- Users who want auto-publish to th.wiki · review-then-paste workflow stays manual

---

## Solution Detail

### Core Capabilities (MoSCoW)

| Priority | Capability | Rationale |
|----------|------------|-----------|
| Must | `wiki-refresh-rules` CLI command scraping all language rule pages from th.wiki to JSON cache | Foundational data layer · Thai-benefits-first steer |
| Must | New port `TransliterationRuleSource` + adapter `WikipediaTransliterationRuleSource` | Hexagonal, swappable for tests |
| Must | New port `TransliterationValidator` + Lite adapter (H1 default) | Judge interface |
| Must | Candidate detection on translated wikitext (deterministic regex, v1) | Cheap, no extra LLM cost |
| Must | New service `transliteration_gate.py` orchestrator | Mirrors `summarize_diff` shape |
| Must | Batched validator call (one LLM call per article, all candidates) | Free-tier compatible without cache |
| Must | review.md gets new section listing verdicts with rule citations | User-facing output |
| Should | CachedValidatorAdapter (Gemini 3 Flash Preview) opt-in via `WIKI_TRANSLATOR_VALIDATOR_MODE=cached` | Phase 5, after Lite proves out |
| Should | Eval corpus seeded by Wannaphong dict (3,868 pairs, free, today); hand-built supplement only after Phase 3 produces real misclassifications worth labeling | FP/recall measurement · per council, don't burn hours on hand-build before knowing if the gate fires correctly |
| Could | Wunsen integration for ja/ko/zh/vi as fast-path validator | Phase 6 optimization |
| Could | LLM-as-detector instead of regex (better recall) | Phase 6 |
| Could | Auto-correction loop (LLM rewrites flagged transliterations inline) | Phase 7, only if v1 verdict accuracy supports it |
| Won't | LangChain wholesale swap | Use google-genai directly |
| Won't | Auto-publish to th.wiki | Review-only stays |
| Won't | Real-time rule refresh per translation | Manual command |
| Won't | Hard-block draft save on parse error in v1 (decide soft-degrade later) | Pending real-use signal |

### MVP Scope

The minimum to validate the hypothesis:

1. `wiki-refresh-rules` populates `~/.cache/wiki-translator/rules/<lang>.json` for at least English
2. Translate one fresh article (Special:Homepage pick)
3. Gate runs after section translation, before save
4. Detection: regex-based candidate finder (Thai-script proper-noun spans next to wikilinks/refs)
5. Validation: LiteValidatorAdapter, batched call with English rule excerpt + all detected candidates
6. Output: review.md gains a "## Transliteration" section listing each candidate with verdict + rule citation
7. **Failure mode**: if the rules cache is missing/corrupt, the gate **soft-degrades** · proceeds without validation, surfaces a loud `⚠️ transliteration validation skipped: <reason>; run wiki-refresh-rules to enable` banner at the top of the review.md transliteration section. Single-user discipline + loud banner carries the safety; mid-flow hard-fail is more disruptive than silent gap with banner.
8. **Eval kickoff**: smoke-test the gate against a small subset of the Wannaphong dict (`wannaphong/thai-english-transliteration-dictionary`, 3,868 pairs with `check==True` flag). Confirm gate fires correctly on known-correct pairs without flagging them. Hand-built corpus only added after the gate produces real misclassifications worth labeling (Phase 4).
9. User reads, validates the verdicts manually (this is the eval moment).

### User Flow

```
1. (one-time, then quarterly refresh) `wiki-refresh-rules`
   ↳ scrapes th.wiki rule pages, writes JSON cache

2. `wiki-translate "<title>"`
   ↳ existing pipeline: fetch, pick source, validate source, translate sections
   ↳ NEW: gate.evaluate(proposed_wikitext, source_lang, rule_cache)
        - detect candidates (regex)
        - batched validator call (1 LLM call, all candidates)
        - aggregate verdicts into TransliterationReport
   ↳ existing: render review.md (now with transliteration section), save draft
   ↳ existing: notify-send

3. User opens review.md, reads transliteration section
   ↳ Approved · paste as-is
   ↳ Flagged · fix in the .wikitext file using rule citation, then paste
```

---

## Technical Approach

**Feasibility: HIGH**

The codebase already has the patterns we need. `summarize_diff` is the exact analog · pure service function, DTO in/out, slots between `_translate_article` (`app/application/use_cases/translate_article.py:176`) and `save_draft` (`:192`). Existing httpx adapter pattern accommodates a 4th MediaWiki adapter.

**Architecture Notes**

- New port + adapter for rule fetching · `TransliterationRuleSource` + `WikipediaTransliterationRuleSource`
- New port + adapter for validation · `TransliterationValidator` with **H1 hybrid** · Lite default, Cached opt-in via `WIKI_TRANSLATOR_VALIDATOR_MODE=lite|cached`
- New service (pure orchestrator, no IO) for gate logic · `app/application/services/transliteration_gate.py`
- New DTOs · `TransliterationCandidate`, `TransliterationVerdict`, `TransliterationReport`
- BS4 + lxml for HTML parsing of rendered MediaWiki content (vs mwparserfromhell · BS4 wins because rule pages are table-heavy and MediaWiki pre-expands templates in HTML mode)
- New CLI command `wiki-refresh-rules` as 4th `[project.scripts]` entry
- Cache path under `~/.cache/wiki-translator/rules/<lang>.json` (configurable via `WIKI_TRANSLATOR_RULES_DIR`)

**Technical Risks**

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Rule-page parsing brittle · th.wiki edits the page, BS4 selectors break | High | Robust selectors with fallbacks; surface parse failures explicitly; last-known-good cache as soft fallback (Phase 2+) |
| Latency budget blow-up · validator call adds time to already-slow translations | Medium | Batched call (1 LLM call per article, not per candidate); validator runs in parallel with `summarize_diff` |
| Verdict accuracy < target · hypothesis fails | Medium | Eval corpus + measurable recall/FP from day one (Phase 4); iterate on prompt or detection if metrics weak |
| Free-tier quota pressure · validator call shares pool with translation | Medium | Single batched call per article ≈ +1 LLM call total; insignificant compared to per-section translation volume (242+ calls/article) |
| Detection misses candidates entirely · "transliteration" not detected → never validated → silent gap | Medium | Conservative regex (over-detect rather than under-detect); FP from detection is fine, missed candidates aren't |
| th.wiki rule pages have gaps for some source languages | Unknown | Soft-degrade per-language ("no rules available for source=ar"); document which languages are first-class |

---

## Implementation Phases

<!--
  STATUS: pending | in-progress | complete
  PARALLEL: phases that can run concurrently (e.g., "with 3" or "-")
  DEPENDS: phases that must complete first (e.g., "1, 2" or "-")
  PRP: link to generated plan file once created
-->

| # | Phase | Description | Status | Parallel | Depends | PRP Plan |
|---|-------|-------------|--------|----------|---------|----------|
| 1 | Rule scraper foundation | `WikipediaTransliterationRuleSource` port + adapter, `wiki-refresh-rules` CLI, BS4 parser, JSON cache writer, tests with `httpx.MockTransport` | complete | with 2 | - | [plan](../plans/completed/transliteration-rule-scraper-foundation.plan.md) · [report](../reports/transliteration-rule-scraper-foundation-report.md) |
| 2 | Validator + detection skeleton | `TransliterationValidator` port + LiteValidatorAdapter, candidate detection regex, `transliteration_gate.py` service, DTOs, unit tests with fakes | complete | with 1 | - | [plan](../plans/completed/transliteration-validator-detection.plan.md) |
| 3 | Integration into use case + review.md | Hook gate into `TranslateArticleUseCase.execute()`, update `_render_review_md()`, integration test against fakes, e2e smoke against ภาษาซีชาร์ป | pending | - | 1, 2 | - |
| 4 | Eval harness + corpus | Wannaphong dict loader + spot-check 20 entries against live th.wiki rules, FP-first measurement script, baseline metrics report; hand-build supplemental corpus only if Phase 3 surfaces misclassifications worth labeling | pending | - | 3 | - |
| 5 | Cached opt-in adapter | `CachedValidatorAdapter` for Gemini 3 Flash Preview, `caches.create` lazy logic, env var routing in bootstrap, free-tier RPM/TPM verification | pending | - | 3 | - |

### Phase Details

**Phase 1: Rule scraper foundation**
- **Goal**: Get th.wiki rule pages out of HTML and into structured per-language JSON files we can quickly look up at translate time
- **Scope**: Port + adapter, CLI command, parser, cache writer. Tests cover happy path (one English page parsed correctly) + parse failure path
- **Success signal**: `wiki-refresh-rules` produces `~/.cache/wiki-translator/rules/en.json` with at least 50 mapped graphemes from the English rule page

**Phase 2: Validator + detection skeleton**
- **Goal**: Have a working `TransliterationValidator` port + Lite adapter that can produce verdicts, plus a regex-based detector that finds candidate transliterations
- **Scope**: Two ports, one adapter, one service file, three DTOs, regex detector, prompt template for batched LLM call. Unit tests with fakes; no real LLM calls in tests
- **Success signal**: Given a fake wikitext with 5 known candidate transliterations and a fake rule excerpt, the service returns a `TransliterationReport` with 5 verdicts

**Phase 3: Integration into use case + review.md**
- **Goal**: End-to-end · `wiki-translate` runs the gate as part of its normal flow, output appears in `<slug>.review.md`
- **Scope**: 5-10 lines of integration in `TranslateArticleUseCase`, update `_render_review_md` template, integration test against fakes, one real-LLM smoke test marked `@pytest.mark.integration`
- **Success signal**: Re-running ภาษาซีชาร์ป produces a draft where `<slug>.review.md` has a populated transliteration section with verdicts on real candidate names

**Phase 4: Eval harness + corpus**
- **Goal**: Quantify gate accuracy · primary metric is FP rate, secondary is recall · validate the hypothesis without burning hours on hand-labeling before the gate proves it fires correctly
- **Scope**:
  1. Load Wannaphong dict (3,868 en/th name pairs, `check==True` subset) as the baseline corpus · `pip install` + JSON munge, single afternoon
  2. Spot-check 20 random Wannaphong entries against the live th.wiki rule pages to confirm Royal-Society conformance hasn't drifted post-2022 (the dict is 4yr stale)
  3. Write eval script that runs the gate against the corpus + computes FP rate, recall, and per-rule-citation accuracy
  4. Baseline metrics report
  5. **Only if Phase 3 surfaces real misclassifications worth labeling**: hand-build supplemental 20-30 cases from those drafts. Don't pre-emptively burn hours.
- **Success signal**: FP rate <10% AND recall ≥75% on Wannaphong baseline, OR concrete misclassification clusters that point at the next iteration (better detection regex, prompt template tweaks, etc.)

**Phase 5: Cached opt-in adapter**
- **Goal**: Provide a path to lower-cost validation (eventually) via Gemini 3 Flash Preview + caches.create
- **Scope**: Second adapter, env var wiring, free-tier verification of new model. NOT default. Triggered by setting `WIKI_TRANSLATOR_VALIDATOR_MODE=cached`
- **Success signal**: `WIKI_TRANSLATOR_VALIDATOR_MODE=cached` works end-to-end on a small article, equivalent verdicts to Lite path, fewer tokens consumed per call

### Parallelism Notes

- **Phases 1 and 2** touch entirely different files and can run in parallel · Phase 1 is in `app/infrastructure/transliteration_rules.py` + new CLI command; Phase 2 is in `app/application/services/transliteration_gate.py` + `app/application/ports.py` additions + LiteValidatorAdapter. No file overlap.
- **Phase 3** depends on both 1 and 2 because integration needs the rule-cache shape AND the validator port stabilized.
- **Phase 4** depends on Phase 3 (need the gate working end-to-end to evaluate).
- **Phase 5** depends on Phase 3 (validator port stabilized; just adds a second adapter behind it).

---

## Decisions Log

| Decision | Choice | Alternatives | Rationale |
|----------|--------|--------------|-----------|
| Source of truth for transliteration rules | th.wiki rule pages | ราชบัณฑิตยสถาน publications direct, ICU, Wunsen, wannaphong dict | User explicit steer · "Thai-benefits-first" |
| HTML parser for rule pages | BS4 + lxml | mwparserfromhell, regex | Tables-heavy content, MediaWiki pre-expands templates in HTML mode |
| Detection algorithm v1 | Deterministic regex | Lexicon lookup, LLM-detector | Cheap, no extra LLM cost, ~70-80% recall acceptable for v1. Council unanimous (Architect + Skeptic + Pragmatist + Critic). |
| Validator call shape | Batched (1 call per article) | Fan-out (1 call per candidate) | Free-tier without cache · batching keeps token volume low |
| Default validator model | Gemini Flash-Lite (existing) | Gemini 3 Flash Preview | Single-model adapter ships first, opt-in to alternatives later |
| Caching strategy v1 | None | `caches.create` on Gemini 3 Flash Preview | Free-tier on Lite has no caching (verified 2026-05-04 against Google docs); using a different model adds complexity not yet justified |
| Cached path | H1 hybrid · adapter-swap via env var | Phase-split per-task, quota-aware fallback | Lowest complexity to ship; swap later if needed |
| Auto-correction in v1 | Out of scope | Auto-rewrite flagged items | Premature; bad verdicts would silently corrupt drafts |
| Failure mode on rule cache miss | **Soft-degrade with loud banner** in review.md (`⚠️ transliteration validation skipped: <reason>; run wiki-refresh-rules to enable`) | Hard-fail (block draft save) | Council flipped this 2026-05-04 · Skeptic + Critic both flagged that hard-fail interrupts mid-flow for a problem orthogonal to the current draft. Single-user discipline + loud banner carries the safety. |
| Refresh trigger | Separate `wiki-refresh-rules` command, manual | Auto-refresh per translation, scheduled cron | Rule pages change rarely; manual is enough |
| LLM SDK choice | Stick with google-genai | LangChain | Existing port already gives provider portability; LangChain conflicts with our hand-rolled retry |
| Eval corpus order | **Wannaphong dict baseline first** (afternoon to wire); hand-built supplement only after Phase 3 produces real misclassifications worth labeling | Hand-built first (laborious, ground-truth) | Council 2026-05-04 · Pragmatist + Skeptic both noted the unpaid-hours-before-knowing-it-works trap. Wannaphong is `pip install` + JSON load; hand-built becomes worth the hours after the gate misclassifies real drafts. |
| Primary success metric | **FP rate <10%** (priority) · recall ≥75% (secondary) | Recall-first framing | Council 2026-05-04 convergent insight (Skeptic + Pragmatist + Critic): a noisy gate that flags 30% of correct names trains the user to dismiss warnings, killing signal. A quiet 75%-recall gate beats a noisy 85%-recall gate. |
| Multi-token candidate definition | Each contiguous Thai-script run = one candidate (multi-word names like "Anders Hejlsberg" → "แอนเดอส์ เฮลส์เบิร์ก" get one verdict) | Per-token verdicts | Simpler prompt, simpler measurement; reassess if Phase 4 metrics suggest split-by-token is more accurate. |
| Parent rule-index resolution | Resolved at Phase 1 build time via `WebFetch` of th.wiki parent page + wikitable enumeration | Pre-emptive scrape during PRD | Just a factual lookup; no architectural decision needed |
| Free-tier RPM/TPM verification for Gemini 3 Flash Preview | Resolved at Phase 5 build time via ai.google.dev/gemini-api/docs/rate-limits + one test call | Live-verify during PRD | Phase 5 is opt-in; not v1-blocking |
| Batched-call prompt template | Iteration during Phase 2 build, against Wannaphong-seeded eval corpus | Lock the template before Phase 2 | Implementation iteration; PRD shouldn't pin the exact phrasing, the corpus and the regex output do |

---

## Council Fallback Plan

If Phase 1-3 proves heavier than scoped (rule-page parsing keeps breaking; LLM-judge prompts don't converge; validator latency too high to swallow), the **Skeptic-line escape hatch** is to ship a 10-line annotator-only gate · zero infrastructure, no validation, just regex-detected candidates surfaced in `review.md` with no verdict. This gives the user the same signal (a list to eyeball) without the rules-cache, validator, eval-harness investment. Cost: an afternoon, not a five-phase build.

When to invoke: if at the end of Phase 1+2 the build estimate for Phase 3 ballooned, OR if Phase 4 metrics fail badly enough that "judge" is the wrong frame and "annotator" was right all along.

This is **not the v1 plan**, but it is the documented retreat path · per the council's Skeptic premise challenge ("the human IS the quality gate; a second automated gate is theater unless we measure first").

---

## Research Summary

**Market Context**

- **No en→th rule-conformant transliterator exists in OSS Python.** Royal Society English rules and th.wiki style guide are prose-only · machine-readable form must be scraped.
- **Wunsen** (MIT, 4yr stale, github.com/cakimpei/wunsen) covers ja/ko/zh/vi with 5 Royal-Society rule sets (ORS61, RI35, RI55, RI49, THC43). Useful as Phase 6 fast-path for those languages, but NOT primary authority.
- **wannaphong/thai-english-transliteration-dictionary** · 3,868 en/th name pairs as TSV with `check` column flagging Royal-Society conformance. Useful as Phase 4 eval supplementary fixture (4yr stale, but data is the value), NOT primary authority.
- **PyThaiNLP 5.3.4** · Python 3.13-compatible, exposes Wunsen via `[wunsen]` extra · the umbrella we'd integrate against in Phase 6.
- **NAACL 2025 paper** (aclanthology.org/2025.loreslm-1.33) · LLM-judge prompt scaffold for transliteration QE in low-resource pairs · adoptable for Phase 2 prompt template.

**Technical Context**

- `summarize_diff` (`app/application/services/diff_summary.py:10-33`) is the exact pattern to mirror · pure service function, DTO in/out, slots between translation and save
- 7 existing ports in `app/application/ports.py:14-84`; adding 2 more (`TransliterationRuleSource`, `TransliterationValidator`) is in-pattern
- All HTTP adapters use `httpx.AsyncClient` with consistent kwargs · 4th MediaWiki adapter for rule pages is trivial
- File-cache pattern is `asyncio.to_thread` wrapping `Path.read_text/write_text`, atomic-rename writes, UTF-8
- `WIKI_TRANSLATOR_*` env-var convention for path/config overrides
- Gemini context caching is **NOT available** on free-tier `gemini-flash-lite-latest` (verified 2026-05-04 against ai.google.dev/gemini-api/docs/pricing). Free caching only on `gemini-3-flash-preview` (non-Lite). Pricing page lists explicit "Context caching price: Not available" for Lite free-tier.

---

*Generated: 2026-05-04*
*Status: DRAFT · ready for `/prp-plan`*
