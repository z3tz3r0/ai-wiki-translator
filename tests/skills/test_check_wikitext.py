"""check_wikitext.py · the mechanical review checks."""

from __future__ import annotations

from pathlib import Path
from types import ModuleType


def test_balance_reports_each_unclosed_construct(checker: ModuleType) -> None:
    issues = checker.balance("{{a}} {{b} [[c]] <ref>x")
    assert any(i.startswith("{{") for i in issues)
    assert any(i.startswith("<ref>") for i in issues)
    assert not any(i.startswith("[[") for i in issues)


def test_self_closing_ref_does_not_count_as_open(checker: ModuleType) -> None:
    assert checker.balance('<ref name="a">x</ref> <ref name="a" />') == []


def test_named_ref_reused_without_definition_is_reported(checker: ModuleType) -> None:
    text = '<ref name="ok">x</ref> <ref name="ok" /> <ref name=lost />'
    assert checker.undefined_named_refs(text) == ["lost"]


def test_mostly_latin_lines_ignore_refs_and_templates(checker: ModuleType) -> None:
    lines = [
        "ข้อความภาษาไทยยาวพอสมควร<ref>{{cite web|title=An English title that is long enough}}</ref>",
        "This sentence was left in English by mistake and is long enough to count.",
    ]
    assert checker.latin_lines(lines) == [2]


def test_soft_signs_need_three_hits_strong_signs_need_one(checker: ModuleType) -> None:
    lines = ["นอกจากนี้ ก", "นอกจากนี้ ข", "แน่นอนครับ"]
    report = checker.sign_report(lines, {"strong": ["แน่นอนครับ"], "soft": ["นอกจากนี้"]})
    assert report == ["STRONG «แน่นอนครับ» lines [3]"]
    report = checker.sign_report([*lines, "นอกจากนี้ ค"], {"soft": ["นอกจากนี้"]})
    assert report == ["SOFT «นอกจากนี้» x3"]


def test_regex_entry_skips_negated_form(checker: ModuleType) -> None:
    buckets = {"mos": ["re:(?<!ไม่)ชัดเจนว่า"]}
    report = checker.sign_report(["ชัดเจนว่าเป็นเช่นนั้น", "ยังไม่ชัดเจนว่าเป็นเช่นไร"], buckets)
    assert report == ["MOS «(?<!ไม่)ชัดเจนว่า» lines [1]"]


def test_number_gap_skips_single_digits_and_numbers_in_refs(checker: ModuleType) -> None:
    source = "Released in 2005 with 3 parts and 1.2 spec.<ref>2026</ref>"
    draft = "เปิดตัวปี 2005"
    assert checker.number_gap(draft, source) == ["1.2"]


def test_report_end_to_end(checker: ModuleType, tmp_path: Path) -> None:
    draft = tmp_path / "d.wikitext"
    draft.write_text("**หนา** \u2014 ข้อความ\nค.ศ. 1953\u20132008 ปี พ.ศ. 2500\n", encoding="utf-8")
    signs = tmp_path / "signs.txt"
    signs.write_text("[strong]\nข้อความ\n[mos]\nปี พ.ศ.\n", encoding="utf-8")
    out = checker.report(draft, None, signs)
    assert "em dashes (U+2014): lines [1]" in out
    assert "en dashes outside ranges (rephrase): lines none" in out
    assert "MOS «ปี พ.ศ.» lines [2]" in out
    assert "markdown leftovers: lines [1]" in out
    assert "STRONG «ข้อความ»" in out


def test_heading_issues_flag_level_one_and_skipped_levels(checker: ModuleType) -> None:
    lines = ["lead", "= Title =", "== A ==", "==== Deep ====", "== B =="]
    assert checker.heading_issues(lines) == ["L2 level-1 heading", "L4 jumps from level 2 to 4"]


def test_bold_is_fine_in_the_lead_only(checker: ModuleType) -> None:
    lines = ["'''โอเพนด็อกคิวเมนต์''' เป็นรูปแบบแฟ้ม", "== ประวัติ ==", "ข้อความ '''หนา''' กลางย่อหน้า"]
    assert checker.bold_outside_lead(lines) == [3]


def test_raw_bucket_sees_urls_inside_references(checker: ModuleType) -> None:
    lines = ["ข้อความ<ref>[https://ex.org/a?utm_source=chatgpt.com ชื่อ]</ref>"]
    buckets = {"raw": ["utm_source=chatgpt.com"], "strong": ["utm_source=chatgpt.com"]}
    assert checker.sign_report(lines, buckets) == ["RAW «utm_source=chatgpt.com» lines [1]"]


def test_en_dash_allowed_in_ranges_and_pairs_only(checker: ModuleType) -> None:
    lines = [
        "ค.ศ. 1953\u20132008",
        "มกราคม 1999 \u2013 ธันวาคม 2000",
        "นิวยอร์ก\u2013ลอนดอน",
        "ข้อความหนึ่ง \u2013 ข้อความสอง",
    ]
    assert checker.stray_en_dashes(lines) == [4]
