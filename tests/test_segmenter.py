"""Structure-aware segmentation: lists and tables stay with their requirement."""

import pytest
from docx import Document

from parsers.pdf_parser import PDFParser
from processors.segmenter import (
    blocks_from_docx,
    blocks_from_pdf,
    blocks_from_text,
    is_skip_section,
    leading_requirement_id,
    segment,
)
from tests.conftest import BASIC_DOCX, LIBRARY_DOC_ORDER, LIBRARY_DOCX, LIBRARY_MD, LIBRARY_PDF, make_docx


def library_segments(kind):
    if kind == "docx":
        blocks = blocks_from_docx(Document(str(LIBRARY_DOCX)))
    elif kind == "pdf":
        blocks = blocks_from_pdf(PDFParser().parse(str(LIBRARY_PDF)))
    else:
        blocks = blocks_from_text(LIBRARY_MD.read_text(encoding="utf-8"))
    segs, report = segment(blocks)
    return {s.requirement_id: s for s in segs if s.requirement_id}, segs, report


# ---------------------------------------------------------------------------
# Requirement IDs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text, rid", [
    ("FR-002 — Add a book", "FR-002"),
    ("NFR-01.1: Normal requests", "NFR-01.1"),
    ("**FR-002 — Add a book**", "FR-002"),
    ("FR-1 The system shall work", "FR-1"),          # known prefix, no separator
    ("(REQ-7) The system", "REQ-7"),
    ("ABC-12: custom prefix with separator", "ABC-12"),
    ("SHA-256 hashing shall be used.", None),          # not an ID
    ("UTF-8 encoding is required", None),
    ("Python 3.8 or later", None),
    ("The system shall", None),
])
def test_leading_requirement_id(text, rid):
    assert leading_requirement_id(text) == rid


@pytest.mark.parametrize("heading, skip", [
    ("1.3 Definitions", True), ("1.4 Definitions and Acronyms", True), ("Table of Contents", True),
    ("2.2 Product Functions", True), ("9. Risks and Future Enhancements", True), ("1.2 Scope", True),
    ("3. Functional Requirements", False), ("5. External Interface Requirements", False),
    ("3.1 FR-01: User Authentication", False), ("3.4 Fines", False),
])
def test_skip_sections(heading, skip):
    assert is_skip_section(heading) is skip


# ---------------------------------------------------------------------------
# The library SRS in all three formats
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["docx", "pdf", "md"])
class TestLibrarySRS:

    def test_exactly_the_39_requirements_in_order(self, kind):
        by_id, segs, _ = library_segments(kind)
        assert [s.requirement_id for s in segs if s.requirement_id] == LIBRARY_DOC_ORDER

    def test_list_items_stay_with_their_requirement(self, kind):
        by_id, _, _ = library_segments(kind)
        fr2 = by_id["FR-002"].text
        for fragment in ("does not contain exactly 10 or 13 characters", "number of copies is less than 1",
                         "later than the current year", "A newly added book shall have all of its copies"):
            assert fragment in fr2
        assert sum(1 for k, _ in by_id["FR-022"].lines if k == "item") == 4
        assert sum(1 for k, _ in by_id["FR-030"].lines if k == "item") == 5
        assert "The fine for a single loan shall not exceed 20.00." in by_id["FR-022"].text

    def test_table_stays_with_its_requirement(self, kind):
        by_id, _, _ = library_segments(kind)
        fr12 = by_id["FR-012"].text
        for value in ("standard", "premium", "staff", "3", "7", "10"):
            assert value in fr12

    def test_requirement_ends_at_next_heading(self, kind):
        by_id, _, _ = library_segments(kind)
        assert "Fines" not in by_id["FR-034"].text.splitlines()[-1]

    def test_glossary_and_metadata_are_not_requirements(self, kind):
        _, segs, report = library_segments(kind)
        texts = " ".join(s.text for s in segs)
        assert "The date by which a loaned copy must be returned" not in texts
        assert "1.3 Definitions" in [s["heading"] for s in report.skipped_sections]

    def test_no_missing_list_warnings(self, kind):
        assert library_segments(kind)[2].warnings == []


def test_docx_table_rendered_as_header_value_items():
    by_id, _, _ = library_segments("docx")
    assert "- Membership type: premium; Borrowing limit: 7" in by_id["FR-012"].text


def test_pdf_sentence_after_a_bullet_is_not_glued_to_it():
    by_id, _, _ = library_segments("pdf")
    lines = by_id["FR-002"].text.splitlines()
    assert lines[-1] == "A newly added book shall have all of its copies available."


# ---------------------------------------------------------------------------
# The Basic SRS: ID'd headings, child requirements, requirement tables
# ---------------------------------------------------------------------------


def test_basic_srs_parent_and_children():
    segs, report = segment(blocks_from_docx(Document(str(BASIC_DOCX))))
    by_id = {s.requirement_id: s for s in segs if s.requirement_id}
    assert by_id["FR-01"].text.startswith("FR-01: User Authentication\nThe system shall provide a mechanism")
    assert by_id["FR-01.1"].parent_id == "FR-01"
    assert by_id["NFR-02.1"].parent_id == "NFR-02"
    assert len([s for s in segs if s.requirement_id]) == 28
    skipped = [s["heading"] for s in report.skipped_sections]
    assert "1.4 Definitions and Acronyms" in skipped and "9. Risks and Future Enhancements" in skipped
    assert all(section.get("items") is not None for section in report.skipped_sections if section["heading"] == "2.2 Product Functions")


# ---------------------------------------------------------------------------
# Synthetic documents for edge cases
# ---------------------------------------------------------------------------


def test_unlabelled_intro_owns_its_bullets(tmp_path):
    def build(doc):
        doc.add_heading("3. Requirements", 1)
        doc.add_paragraph("The system shall reject an upload when:")
        doc.add_paragraph("the file is larger than 10 MB;", style="List Bullet")
        doc.add_paragraph("the file type is not PDF.", style="List Bullet")
        doc.add_paragraph("The system shall log every upload.")
    segs, _ = segment(blocks_from_docx(Document(make_docx(tmp_path, build))))
    assert [s.text for s in segs] == [
        "The system shall reject an upload when:\n- the file is larger than 10 MB;\n- the file type is not PDF.",
        "The system shall log every upload.",
    ]


def test_bullets_without_an_intro_stay_separate(tmp_path):
    def build(doc):
        doc.add_heading("3. Requirements", 1)
        doc.add_paragraph("The system shall allow login.", style="List Bullet")
        doc.add_paragraph("The system shall allow logout.", style="List Bullet")
    segs, _ = segment(blocks_from_docx(Document(make_docx(tmp_path, build))))
    assert [s.text for s in segs] == ["The system shall allow login.", "The system shall allow logout."]


def test_requirement_table_rows_become_requirements(tmp_path):
    def build(doc):
        doc.add_heading("4. Security Requirements", 1)
        table = doc.add_table(rows=3, cols=3)
        for r, row in enumerate([["ID", "Type", "Requirement"],
                                 ["SEC-1", "Security", "Passwords shall be hashed."],
                                 ["SEC-2", "Security", "Sessions shall expire after 30 minutes."]]):
            for c, value in enumerate(row):
                table.cell(r, c).text = value
    segs, _ = segment(blocks_from_docx(Document(make_docx(tmp_path, build))))
    assert [(s.requirement_id, s.text) for s in segs] == [
        ("SEC-1", "SEC-1: Passwords shall be hashed. (Type: Security)"),
        ("SEC-2", "SEC-2: Sessions shall expire after 30 minutes. (Type: Security)"),
    ]


def test_key_value_tables_are_skipped_and_reported(tmp_path):
    def build(doc):
        table = doc.add_table(rows=2, cols=2)
        table.cell(0, 0).text, table.cell(0, 1).text = "Version", "1.0"
        table.cell(1, 0).text, table.cell(1, 1).text = "Author", "Team"
        doc.add_paragraph("The system shall export reports.")
    segs, report = segment(blocks_from_docx(Document(make_docx(tmp_path, build))))
    assert [s.text for s in segs] == ["The system shall export reports."]
    assert report.skipped_tables and report.skipped_tables[0]["first_row"] == ["Version", "1.0"]


def test_missing_list_is_reported(tmp_path):
    def build(doc):
        doc.add_paragraph("FR-9 — Limits The limits shall be as follows:")
        doc.add_heading("4. Next", 1)
    segs, report = segment(blocks_from_docx(Document(make_docx(tmp_path, build))))
    assert report.warnings[0]["type"] == "missing_list" and report.warnings[0]["requirement_id"] == "FR-9"


def test_ids_in_skipped_sections_are_kept(tmp_path):
    def build(doc):
        doc.add_heading("1.2 Scope", 2)
        doc.add_paragraph("The product covers lending.")
        doc.add_paragraph("FR-50: The system shall support lending.")
    segs, report = segment(blocks_from_docx(Document(make_docx(tmp_path, build))))
    assert [s.requirement_id for s in segs] == ["FR-50"]
    assert report.skipped_sections[0]["items"] == ["The product covers lending."]


def test_markdown_text_input():
    text = (
        "## 3.1 Catalog\n\n"
        "**FR-12 — Limits**\nThe limit shall depend on the tier:\n\n"
        "| Tier | Limit |\n|---|---|\n| standard | 3 |\n| premium | 7 |\n\n"
        "**FR-13 — Reject**\nThe system shall reject a book when:\n- the ISBN is invalid;\n- copies < 1.\n"
    )
    segs, _ = segment(blocks_from_text(text))
    by_id = {s.requirement_id: s.text for s in segs}
    assert by_id["FR-12"] == ("FR-12 — Limits The limit shall depend on the tier:\n"
                              "- Tier: standard; Limit: 3\n- Tier: premium; Limit: 7")
    assert by_id["FR-13"].endswith("- the ISBN is invalid;\n- copies < 1.")
