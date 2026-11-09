---
name: thwiki-publish-prep
description: Stage a reviewed Thai Wikipedia edit in the owner's Chrome for the owner to publish. Writes the attribution and LLM-disclosure edit summary, pastes the approved wikitext into the th.wikipedia.org edit form, opens the diff, and stops before saving. Then offers the talk-page translation notice and logs the edit. Use after thwiki-review, when the owner has approved the review packet.
---

# thwiki-publish-prep

Load `thwiki-rules` first. Hard limits for this skill:

- **Never save.** Never click `wpSave`, never call the edit API, never use a bot. The owner
  reads the diff and presses เผยแพร่ (publish) themselves.
- Never revert a revert. If the edit was undone, open the talk page and report, do not redo it.
- Start only when the owner has said the review packet is approved.

Browser: the `chrome-kittipan` MCP (the owner's logged-in Chrome on CDP port 9223,
started with `cdp-chrome kittipan`).

## 1. Edit summary (one line, Thai)

Fill in, keep it under one line, never vague (วิธีใช้:ความย่อการแก้ไข):

| Edit | Summary |
|---|---|
| whole article translated | `การแก้ไขนี้เป็นการแปลบทความวิกิพีเดียภาษาอังกฤษ [[:en:{EN}]] รุ่น {EN_REVID}; เครดิตดูที่หน้าประวัติ · ใช้ Gemini ({MODEL}) และ MinT ช่วยแปล ตรวจทานโดยผู้แก้ไข` |
| some sections translated (update, expand) | `ปรับปรุงเนื้อหา โดยบางส่วนแปลจากบทความวิกิพีเดียภาษาอังกฤษ [[:en:{EN}]] รุ่น {EN_REVID}; เครดิตดูที่หน้าประวัติ · ใช้ Gemini ({MODEL}) และ MinT ช่วยแปล ตรวจทานโดยผู้แก้ไข` |

`{MODEL}` is the model the CLI ran with (`gemini-flash-lite-latest` unless the owner pinned one).
The first row is the wording วิกิพีเดีย:การแปลภาษา recommends, plus the revision id and the
LLM disclosure วิกิพีเดีย:แบบจำลองภาษาขนาดใหญ่ requires. Show the summary to the owner.

## 2. Stage the edit (no article text through tool calls)

1. Put the file on the clipboard, zero tokens:
   PowerShell `Set-Clipboard -Value (Get-Content -Raw -Encoding UTF8 '<workdir>\<slug>.merged.wikitext')`.
   Tell the owner this replaced their clipboard.
2. `navigate_page` to `https://th.wikipedia.org/w/index.php?title=<Thai title>&action=edit`.
3. `evaluate_script`: return `mw.config.get('wgUserName')`. Not the owner's account: stop.
4. Focus the edit box with `evaluate_script` (`document.getElementById('wpTextbox1').focus()`,
   or the CodeMirror content element when syntax highlighting is on), then `press_key`
   `Control+A`, then `press_key` `Control+V`.
5. `evaluate_script`: set `#wpSummary` to the summary, then click `#wpDiff` (show changes).
6. `evaluate_script`: return the length of the edit box text and the diff table row count. Report
   both. If the length is far from the file size, say so, the paste may have failed.
7. Tell the owner: the diff is open, read it, press เผยแพร่ if it looks right.

## 3. After the owner publishes

- Get the new Thai revision id (API `prop=revisions` on the title).
- Offer the talk-page notice (same staging steps, prepend to `พูดคุย:<Thai title>`):
  `{{หน้าที่ถูกแปล|en|{EN}|version={EN_REVID}|insertversion={TH_REVID}}}`, add `|partial=yes`
  for an update or expand. Summary: `เพิ่มแม่แบบหน้าที่ถูกแปล`.
- New article only (future mode): link the Wikidata item to the new Thai page, using the
  Wikidata MCP to find the item and the owner's Chrome to add the sitelink.
- Append one line to `~/Documents/wiki-translations/ledger.tsv` (create with a header if absent):
  `date	thai_title	mode	en_title	en_revid	th_revid	model`. A later skill learns from the
  edits other people make to these articles.
