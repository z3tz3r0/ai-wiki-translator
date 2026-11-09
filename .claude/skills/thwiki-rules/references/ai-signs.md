# AI-writing signs th.wiki patrollers look for

From วิกิพีเดีย:สัญญาณของการเขียนด้วยปัญญาประดิษฐ์ (rev 13277686), paraphrased. The page itself
says these signs alone are not grounds for speedy deletion, and that detectors (GPTZero,
Pangram) and gut feeling are unreliable. Pages made by an LLM with no human review can be
deleted under G15. Use this list to find what to fix, not to judge.

`thwiki-review/scripts/check_wikitext.py` catches the mechanical ones (marked ⚙). The rest
need a reader.

## Content

- **Regression to the mean**: specific, unusual facts flattened into generic praise that could
  describe anything. Compare with the English: a translation must keep the specifics.
- **Inflated importance**: tying an ordinary subject to legacies, wider debates, conservation
  status or public discussion the sources do not make.
- **Notability talk in the prose**: describing the media coverage itself ("การนำเสนอข่าวจาก
  แหล่งอิสระ", "มีการเคลื่อนไหวบนโซเชียลมีเดียอย่างต่อเนื่อง") instead of the subject.
- **Superficial analysis**: a significance clause tacked onto a fact, often a trailing "กำลัง ..."
  phrase, sometimes pinned on a named source that never said it.
- **Promotional or brochure tone**, recurring "มรดกทางวัฒนธรรม", superlatives used as praise.
- **Vague attribution**: "นักวิจารณ์", "นักวิชาการ" with one source behind it, or an inflated consensus.
- **Formulaic endings**: a "ความท้าทาย" (challenges) section weighed against vague positives,
  then "แนวโน้มในอนาคต" (future prospects). ⚙ as headings.
- **Lead that treats a list or broad title as a proper noun**: "X หมายถึง ...", "X คือรายชื่อ ...".
  Introduce the subject naturally instead.
- **Boilerplate headings** such as "รางวัลและการยกย่อง", "การนำเสนอข่าว". ⚙ for the first.

## Formatting

- A heading that repeats the article title before the lead. Level-1 headings in the body,
  skipped levels (`===` straight after the lead). ⚙ Markdown leftovers: `----` rules,
  Markdown tables inside wikitables, `↩` back-links. ⚙
- Bold scattered through the prose like slides, and vertical lists with a bold inline header and
  a colon, using `•`, `-`, an en dash (U+2013), `#`, `1.` or emoji. ⚙ for bold outside the lead and `•`.
- Em dashes everywhere in place of commas, parentheses or colons, often with spaces around
  them. ⚙ (all em dashes are listed)
- Curly quotes and apostrophes, or a mix with straight ones. ⚙
- Emoji in headings or bullets. Tiny tables that should be prose or an infobox.

## Citations

- Chatbot tracking parameters in URLs: `utm_source=chatgpt.com`, `utm_source=openai`,
  `utm_source=copilot.com`, `referrer=grok.com`. ⚙ (scanned inside references)
- Dead links missing from the Internet Archive, invalid ISBN checksums, DOIs that fail or point
  to unrelated papers, book citations with no page number or URL.
- Broken reference reuse, named references used but never defined, list-defined references
  never cited. ⚙ for undefined named references.
- Converting bare links into citation templates without checking the source.

## Signs of human writing (do not "fix" these away)

- Plain verbs (เขียน, ย้าย, ใช้, พยายาม) over stiff synonyms (บรรจงเขียน, ย้ายถิ่นฐาน,
  นำไปใช้ประโยชน์, พยายามกระทำ). Ordinary constructions (มี ..., มาก, อาจจะ, เพื่อที่จะ,
  อันเป็นผลมาจาก) are normal Thai and fully acceptable.
- Text added before ChatGPT's public launch (30 November 2022), checkable with WikiBlame.
- An editor who can explain each choice and show the real source when asked. The owner must be
  able to do this for every published sentence.
