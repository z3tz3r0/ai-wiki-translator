# Thai Wikipedia style, for writing and reviewing Thai text

From วิกิพีเดีย:คู่มือการเขียน (rev 13162846) and its tutorial วิธีใช้:สอนคู่มือการเขียน/1 to /6.
Paraphrased. When a rule here and the page disagree, the page wins: run `check_sources.py`.
Principles from the tutorial: consistent within an article, stable (do not restyle text that
already follows the guide), clear, and every fact verifiable from its reference.

## Layout

- Lead first, no heading. 1 to 4 paragraphs that summarise the article on their own. The first
  sentence defines the subject and says why it matters. Hatnotes at the very top, infobox
  before the lead text. Infoboxes and lead images sit on the right.
- Headings start at `==`, at most `=====`, never `=`. Do not skip a level (`==` then `====`).
  Headings are short and unique, do not repeat the article title, and hold no links, `<ref>`,
  images or questions.
- Sections read best at 1 to 4 paragraphs.
- End sections, in order: `ดูเพิ่ม`, `อ้างอิง`, `แหล่งข้อมูลอื่น` ("External links" is always
  `แหล่งข้อมูลอื่น`). External links never go in the prose.
- Keep the article's existing citation style, do not mix styles. `<ref>` goes straight after
  the punctuation mark, no space before it.
- Images: thumbnail, right-aligned by default, with a caption that adds context. Spread them
  out, do not stack many in a short section.

## Language

- No first or second person (ผม, ฉัน, คุณ, ผู้อ่าน) outside quotations and titles. No
  instruction phrasing (สังเกตว่า, ควรทราบว่า, พึงตระหนักว่า). Avoid แน่นอน, ในความเป็นจริง,
  ชัดเจนว่า, and do not present a fact with อ้างว่า.
- Pronouns: เขา or เธอ for people, พระองค์ for royalty, มัน for animals.
- Nationalities and languages follow the country name (ชาวสวีเดน, not ชาวสวีดิช), except
  established dictionary forms (เยอรมัน, กรีก, อังกฤษ, อเมริกัน).
- "United States" is สหรัฐ. "List" is รายการ, รายชื่อ, รายพระนาม or รายพระนามและชื่อ.
- Emphasis: italics, sparingly, never bold. Bold is for the title words in the lead. An article
  with two names, such as a translated subject, bolds both.
- Translating a foreign quotation yourself: write natural modern Thai and always include the
  original text, in italics.

## Foreign terms and transliteration

- Use as few foreign terms as possible. Order of authority for a transliteration: Thai
  Wikipedia consensus (คำทับศัพท์ในวิกิพีเดีย), then dictionaries, then the Royal Society's
  rules (ราชบัณฑิตยสภา). An official Thai spelling beats the rules.
- No tone marks on loanwords, except Chinese and Vietnamese, dictionary words and registered names.
- A multi-word foreign name transliterates as one unbroken word (เซาท์พาร์ก), except a
  person's given name and surname, and a maker plus product (ไมโครซอฟท์ วินโดวส์).
- First mention: Thai term, then the original in parentheses, as th.wiki articles do:
  `โอเพนด็อกคิวเมนต์ (อังกฤษ: OpenDocument)`. Tag foreign text with `{{lang|<code>|...}}`.
- First use of an abbreviation: full term, then the abbreviation in parentheses. Never invent a
  Thai abbreviation for a translated organisation name, keep the official one.

## Numbers, dates, units

- Years: `พ.ศ. 2547`, `ค.ศ. 1999`, a space after the era, never `ปี พ.ศ.` or `ปี ค.ศ.`.
  Decades without ที่ (`พุทธทศวรรษ 2550`).
- Arabic numerals. Commas every three digits, except in years. A space before and after a
  number in running Thai text. "billion" becomes พันล้าน, หมื่นล้าน or แสนล้าน.
- Write `ที่ 1`, never `#1`.
- Times `hh:mm น.`, or `hh:mm:ss` without น.
- Avoid words that go stale (ปัจจุบัน, ล่าสุด): give the year ("ณ ค.ศ. 2025").
- SI units. Write ต่อ, not `/` (เมตรต่อวินาที). Drop non-SI units carried over from English
  (ไมล์, ปอนด์) when they add nothing. Join a number to its unit symbol with `{{nbsp}}`.

## Punctuation and spacing

- Straight quotes `"` and `'`, never curly quotes, guillemets or backticks. Double outside,
  single inside.
- Italics for major works (books, films, TV series, games, albums, paintings) and scientific
  names. Quotation marks for short works (articles, chapters, songs, episodes, poems).
- Quotes over 40 words or several paragraphs go in `{{quote}}` without quotation marks.
- Spaces outside parentheses, none inside. Spaces before and after ๆ unless punctuation
  follows. A space after ฯ. No commas in Thai lists or in place names
  (กรุงเทพมหานคร ประเทศไทย), but use a comma where a reader could misparse the sentence.
- Minus sign `−` (U+2212), not a hyphen.
- **Dashes (owner decision A, 2026-11-09).** In article text, follow the guide for ranges and
  pairs: an en dash (U+2013) with no spaces between numbers or years (ค.ศ. 1953, en dash,
  2008; หน้า 14, en dash, 21) and between paired names (นิวยอร์ก, en dash, ลอนดอน), and a
  spaced en dash between different units (มกราคม 1999, space, en dash, space, ธันวาคม 2000).
  Never a hyphen in place of a dash. No dash inside a sentence: rephrase with a comma,
  parentheses or a new sentence. th.wiki's AI-signs page lists em dashes as a chatbot tell.
  The owner's no-dash rule covers chat and repo files, not article text.
- Prevent a bad line break with `{{nowrap}}` or `{{ไม่ตัดคำ}}`.

## Links

- Link a key term on its first mention in a topic, when a reader would want that article or the
  term needs explaining. Do not over-link, and prefer a short explanation in parentheses to a
  string of links.
- External links only in `แหล่งข้อมูลอื่น`, and only when highly relevant or adding detail the
  article has no room for. Links that support a statement are references, in `อ้างอิง`.
