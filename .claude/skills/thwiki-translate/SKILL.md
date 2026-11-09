---
name: thwiki-translate
description: Bring an existing Thai Wikipedia article up to date or expand it from its English counterpart, using this repo's Gemini CLI for the translation and keeping the existing Thai text. Use for th.wiki suggested edits of type "update" or "expand", or when the owner names a Thai article to update from English. Produces a merged wikitext draft and hands it to thwiki-review. Never edits Wikipedia.
---

# thwiki-translate

Load `thwiki-rules` first (`.claude/skills/thwiki-rules/SKILL.md`). This skill works inside
those limits: Gemini translates, you plan and assemble, the owner reviews and publishes.

## Modes

| Mode | When | Status |
|---|---|---|
| update | Thai article exists, English is newer (Growth task `update`) | supported |
| expand | Thai article is a stub, English covers more (Growth task `expand`) | supported, same steps |
| new | no Thai article yet | not supported: `wiki-translate` starts from a Thai title and its language links. Say so and stop |
| Thai-only topic | no English article | not this skill |

## Token rules

- Never read the whole English article. Read outlines, then `--extract` only the sections you move.
- Read the whole Thai article you are editing when it is short (WP:CAREFUL asks for it). For a
  long one, read the sections you touch and their neighbours.
- Never read the `## Diff` part of `<slug>.review.md`: for an update it is a whole-article line diff, all noise. Read only the header above it.
- One plan, one owner approval. Do not iterate on wording here, that is `thwiki-review`.

## Steps

Workdir: `~/Documents/wiki-translations/<YYYY-MM-DD>/<slug>/`, the folder the CLI writes to.
`<slug>` is the Thai title with spaces turned into `-` (Thai characters kept).

1. **Rule freshness.** `python -X utf8 -I .claude/skills/thwiki-rules/scripts/check_sources.py`.
   Any `CHANGED` line: read only that diff link, tell the owner what changed, then continue.

2. **Pre-flight, no article text read.**
   - Wikidata MCP: the item for the Thai title. The biography-of-living-persons policy applies
     when P31 has Q5 (human) and either P569 (birth) is within the last 115 years with no P570
     (death), or P570 is within the last 2 years. Then tell the owner, keep every added
     sentence's reference, and add nothing contentious without an inline source.
   - Thai article via API (`prop=info&inprop=protection|talkid`, `prop=categories`):
     protected, in `หมวดหมู่:บทความคัดสรร` or `หมวดหมู่:บทความคุณภาพ`, or talk page edited in the
     last 30 days means careful mode: report it and ask before drafting (WP:CAREFUL).

3. **Start the translation in the background** (it takes minutes, Gemini quota, no Claude tokens):
   `PYTHONUTF8=1 uv run wiki-translate "<Thai title>" --source-lang en` with `run_in_background`.
   Do not pipe it through `tail` or similar: that hides the exit code. Without `PYTHONUTF8=1`
   Windows prints to a pipe in cp1252 and the CLI crashes on the Thai summary line after saving
   (`app/interfaces/cli/main.py:69`).
   If the owner keeps a glossary, add `--glossary <path>`.

4. **Outline both articles while it runs.**
   `python -X utf8 -I .claude/skills/thwiki-translate/scripts/outline.py th:<Thai title> en:<English title> --save <workdir>`
   Columns: section index, level, characters, `<ref>` count, latest year outside references.
   Note both revision ids from the header lines: the English one goes in the edit summary.

5. **Merge plan.** Write `<workdir>/<slug>.plan.md`, a short table:
   - each English section: covered by which Thai section, missing, or Thai outdated (year lags)
   - each Thai section: keep, extend, or replace (with the reason)
   Rules: keep every sourced Thai sentence. Where English has newer sourced facts that
   contradict Thai, add the newer fact and list the old sentence for the owner, never delete it
   silently. A removal the owner approves goes to a talk-page note (WP:CAREFUL). Skip sections
   that would add no value for Thai readers, and say which ones you skipped and why.
   Show the plan to the owner and wait for approval.

6. **Assemble.** When the CLI finishes, read the `<slug>.review.md` header (stop at `## Diff`).
   Gate `rejected_source`: stop and report the reasons.
   Otherwise outline the draft: `outline.py <workdir>/<slug>.wikitext`. Its sections follow the
   English order, so English section N maps to draft section N.
   Build `<workdir>/<slug>.merged.wikitext` from the saved current Thai wikitext, inserting or
   replacing whole sections with blocks from `outline.py <draft> --extract "<draft heading>"`.
   Move blocks, do not rewrite prose here. Keep the Thai article's existing infobox, categories,
   interlanguage and maintenance templates unless the plan says otherwise. Remove a maintenance
   template (such as the update notice) only when the plan covers what it asked for.

7. **Hand off** to `thwiki-review` with the merged file, the saved English wikitext, and the
   plan. Record the English revision id and the model version for `thwiki-publish-prep`.
