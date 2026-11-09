---
name: thwiki-rules
description: Thai Wikipedia rules every th.wiki skill in this repo works inside. AI and translation policy, attribution and LLM-disclosure edit summaries, bold versus careful editing, and pointers to the detailed content-policy, style and AI-signs references. Load before translating, reviewing, researching or staging any edit for th.wikipedia.org.
---

# thwiki-rules

English paraphrase of Thai Wikipedia pages, not copied text (their text is CC BY-SA).
`sources.tsv` lists each page with the revision it was read at. At the start of a session run
`python -X utf8 -I .claude/skills/thwiki-rules/scripts/check_sources.py`; for a `CHANGED`
page read only the diff link it prints, then update the rule here.

## Load the reference you need, not all of them

| File | Load when |
|---|---|
| `references/content.md` | choosing what to add or keep: neutrality, verifiability, sources, living people, titles, speedy deletion |
| `references/style.md` | writing or reviewing Thai text: layout, transliteration, numbers, dates, punctuation, links |
| `references/ai-signs.md` | reviewing: the AI-writing signs th.wiki patrollers look for |

## What AI may do

- Translate, and copyedit the editor's own text. Nothing else: no AI-written new article
  content, no AI-written talk comments, no opaque AI edit summaries (วิกิพีเดีย:แบบจำลองภาษาขนาดใหญ่).
- Name the LLM in every edit summary, even when the model's terms do not require it.
- No raw machine translation. Pages that read like Google Translate output get deleted, and
  repeating it can get the account blocked (วิกิพีเดีย:การแปลภาษา). Unreadable or machine-like Thai
  is speedy-deletion criterion บ2. A human reads every sentence before it is published.
- Keep wiki markup. Large plain-text pastes get watched or reverted.
- Thai Wikipedia's standards can differ from English Wikipedia's: an English article can fail
  Thai criteria. Check notability and sources, do not assume.

## Attribution

- Edit summary: credit `[[:en:<Title>]]` with its revision id, `เครดิตดูที่หน้าประวัติ`, and the
  LLM used. Exact formats are in `thwiki-publish-prep`. One line, specific, never vague
  ("แก้ไขบางจุด" says nothing) (วิธีใช้:ความย่อการแก้ไข).
- Interlanguage link through Wikidata.
- Talk page: `{{หน้าที่ถูกแปล|en|<Title>|version=<en revid>|insertversion=<th revid>}}`,
  with `|partial=yes` when only part was translated.

## Bold or careful (วิกิพีเดีย:ขอให้กล้า)

- New article: be bold, publish once it passes review.
- Existing article: careful. Read the whole Thai article and its talk page first. Featured
  (`หมวดหมู่:บทความคัดสรร`), good (`หมวดหมู่:บทความคุณภาพ`), protected or disputed articles need
  the owner's go-ahead and often consensus on the talk page first.
- Keep sourced Thai content. Neutrality policy: do not remove sourced material because it
  looks biased, rewrite it neutrally. Large removals go to the talk page with the reason.
- Being bold never excuses breaking the living-persons policy, even briefly.
- Never revert a revert. Discuss on the talk page. Do not take reverts personally.
- Learn from how others edit these articles, so the same mistake is not repeated.

## Repo limits

- Never write to Wikipedia. The owner presses publish.
- Never cite Wikipedia, in any language, as a source. Carry the English article's citations
  over as they are, and flag contentious claims for the owner to spot-check.
- Formal encyclopedic Thai. thai-humanizer's pattern lists apply, its personality section does
  not (it adds opinion, which breaks neutrality).
