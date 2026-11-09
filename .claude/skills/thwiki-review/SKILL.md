---
name: thwiki-review
description: Review a Thai Wikipedia draft before the owner publishes it. Runs mechanical wikitext checks, sends English and Thai section pairs to the independent wiki-reviewer agent, applies Thai style and manual-of-style fixes, and writes a short packet listing only what needs the owner's decision. Use after thwiki-translate, or on any Thai wikitext the owner wants checked.
---

# thwiki-review

Load `thwiki-rules` first. The packet you write does not replace the owner reading the diff
before publishing (thwiki-publish-prep shows it). It cuts the owner's reading to the spots
that need a decision.

## Inputs

From `thwiki-translate`: `<workdir>/<slug>.merged.wikitext`, the saved English wikitext, the
draft `<slug>.wikitext`, and `<slug>.plan.md` (which sections were translated).

## Steps

1. **Pair the translated sections.** For each section the plan inserted or replaced, write
   `<workdir>/review/<n>.en.wikitext` and `<n>.th.wikitext` with
   `python -X utf8 -I .claude/skills/thwiki-translate/scripts/outline.py <file> --extract "<heading>"`.
   Review only new text. Existing Thai text was already on the wiki.

2. **Mechanical checks**, per pair and once on the merged file:
   `python -X utf8 -I .claude/skills/thwiki-review/scripts/check_wikitext.py <th> --source <en>`
   On the merged file, run it without `--source` (the number check only makes sense per pair).
   It reports markup balance, named refs used but never defined, em dashes, en dashes outside ranges,
   Markdown leftovers, untranslated English lines, phrases from `ai_signs_th.txt`, numbers
   lost in translation, and the reference counts on each side.

3. **Independent review.** Spawn the `wiki-reviewer` agent once, with only the pair file paths.
   Give it no plan, no notes, no opinion of your own: it must not be anchored on how the draft
   was made.

4. **Style pass** on the lines the checks or the reviewer flagged, not the whole text.
   Use `thai-humanizer` pattern sections 1 to 17 and `references/banned-words-th.md`, plus the
   style rules in `thwiki-rules`. Formal encyclopedic register. Never use thai-humanizer's
   personality section or its draft, "what still looks AI", final output format: they break
   neutrality. Never add a claim, never change meaning, never drop a `<ref>` or template.

5. **Apply** to `<slug>.merged.wikitext`:
   - mechanical fixes (markup, Markdown, curly quotes, era words, units) directly
   - reviewer MUST-FIX items when the fix is unambiguous
   - everything else goes to the packet
   Then re-run check 2 on the merged file. It must show balance ok, no undefined named refs,
   no Markdown, no STRONG hits, no em dashes, no en dashes outside ranges (rephrase those as
   `references/style.md` says: owner decision A keeps en dashes only in ranges and pairs).

6. **Packet**: `<workdir>/<slug>.packet.md`, at most about 40 lines:
   - header: Thai title, mode, English title and revision id, sections changed, BLP yes or no
   - **Decide**: items only the owner can settle (meaning doubts, terms, removed or contradicted
     Thai sentences from the plan), each one line with the merged-file line number
   - **Applied**: one line per change made in step 5
   - **Checks**: the final check_wikitext summary lines
   Show the packet. When the owner approves, hand off to `thwiki-publish-prep`.
