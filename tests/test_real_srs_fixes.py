"""Segmentation fixes found by running real SRS documents (Virtual Clinic, AcRe, Books Recommender)."""

import pytest

import app
from parsers.input_adapter import InputAdapter
from processors.segmenter import (
    blocks_from_pdf,
    blocks_from_text,
    is_skip_section,
    is_toc_line,
    leading_requirement_id,
    parent_of_id,
    segment,
)


def segments_of(text):
    segs, report = segment(blocks_from_text(text))
    return segs, report


# --- tables of contents -----------------------------------------------------


def test_contents_entries_are_skipped_and_do_not_end_the_contents_section():
    segs, report = segments_of(
        "Table of Contents\n"
        "1. Introduction  4\n"
        "Purpose ........ 4\n"
        "2. Overall Description 7\n"
        "Performance Requirements……………27\n"
        "\n"
        "1. Introduction\n"
        "3. Functional Requirements\n"
        "FR-1: The system shall store books.\n"
    )
    assert [s.requirement_id for s in segs] == ["FR-1"]
    assert len(report.toc_lines) == 4


@pytest.mark.parametrize("line, in_toc, expected", [
    ("Methodology………………...……….15", False, True),          # leader straight into the number
    ("......................................4", False, True),
    ("Overview  6", True, True),                               # plain page number inside a contents list
    ("Overview  6", False, False),                             # ... but not elsewhere
    ("The system shall respond within 5", True, False),       # requirement wording is never an entry
    ("Response time .... must be under 2", False, False),
])
def test_toc_line_detection(line, in_toc, expected):
    assert is_toc_line(line, in_toc) is expected


# --- IDs ----------------------------------------------------------------------


@pytest.mark.parametrize("text, rid", [
    ("Section-2 - It describes the product perspective", None),
    ("Figure-3: Use case diagram", None),
    ("Step-1: Open the page", None),
    ("Req-1/2 Edit Speciality View and update", "Req-1/2"),
    ("FR-3.1: The system shall load the file.", "FR-3.1"),
])
def test_document_part_numbers_are_not_requirement_ids(text, rid):
    assert leading_requirement_id(text) == rid


def test_sub_ids_become_children_of_an_earlier_parent():
    segs, _ = segments_of(
        "Req-1 Maintain Specialities This functionality will maintain specialities\n"
        "Req-1/1 Add Speciality Add a new speciality\n"
        "Req-1/2 Edit Speciality Update an existing speciality\n"
        "FR-3.1: The system shall load the file.\n"
    )
    parents = {s.requirement_id: s.parent_id for s in segs}
    assert parents == {"Req-1": None, "Req-1/1": "Req-1", "Req-1/2": "Req-1", "FR-3.1": None}
    assert parent_of_id("Req-1/2") == "Req-1" and parent_of_id("FR-001") is None


# --- report-style sections ----------------------------------------------------


@pytest.mark.parametrize("heading, skipped", [
    ("7. Implementation and Testing", True),
    ("8. Results and Discussion", True),
    ("9. Conclusion", True),
    ("7.5. Evaluation and Analysis", True),
    ("6. Summary", True),
    ("3.4 Search Results", False),            # a feature, not a report section
    ("3.2 Discussion Forum", False),
    ("5.1 Testing Requirements", False),      # mentions requirements: never skipped
])
def test_report_sections_after_the_specification_are_skipped(heading, skipped):
    assert is_skip_section(heading) is skipped


# --- list introductions and duplicates ---------------------------------------


def test_unlabelled_introduction_without_its_list_is_reported_not_emitted():
    segs, report = segments_of(
        "3. Other Requirements\n"
        "The following documents shall be prepared:\n"
        "\n"
        "4. Interfaces\n"
        "FR-9: The system shall support these formats:\n"
    )
    assert [s.requirement_id for s in segs] == ["FR-9"]          # labelled introduction is kept
    dropped = [w for w in report.warnings if w["dropped"]]
    assert len(dropped) == 1 and dropped[0]["text"].startswith("The following documents")


def test_repeated_text_is_dropped_but_distinct_ids_are_kept():
    segs, report = segments_of(
        "5.1 Backup\n"
        "The system data shall be backed up every night.\n\n"
        "5.2 Business Rules\n"
        "BR-1: Each doctor has one speciality.\n\n"
        "BR-2: Each doctor has one speciality.\n\n"
        "5.3 Software Quality Attributes\n"
        "The system data shall be backed up  every night!\n"
    )
    assert [s.requirement_id for s in segs] == [None, "BR-1", "BR-2"]
    assert len(report.duplicates) == 1


# --- PDF running headers / footers -------------------------------------------


def test_running_headers_and_footers_are_removed():
    pages = [{"page": n, "text": f"SRS for Virtual Clinic Page {n}\n"
                                 f"FR-{n}: The system shall do thing {n}.\n"
                                 "National Institute of Technology 2018"} for n in range(1, 5)]
    texts = [b.text for b in blocks_from_pdf({"pages": pages})]
    assert texts == [f"FR-{n}: The system shall do thing {n}." for n in range(1, 5)]


# --- Markdown / text files ----------------------------------------------------


def test_markdown_and_text_files_are_read_as_documents(tmp_path):
    md = tmp_path / "spec.md"
    md.write_text("# SRS\n## 3. Requirements\nFR-1: The system shall work.\n", encoding="utf-8")
    adapted = InputAdapter().adapt(str(md))
    assert adapted["type"] == "textfile"
    document = app.parse_input(adapted["data"], adapted["type"])
    assert document["file_name"] == "spec.md" and "FR-1" in document["text"]
    assert InputAdapter().detect(str(md.with_suffix(".txt").write_text("x") and md.with_suffix(".txt"))) == "textfile"


# --- round 2: ProClinic, Health Management System, NexusERP, Travel Agency ---


@pytest.mark.parametrize("text, rid", [
    ("FR-AUTH-01 (User Registration): Any guest can register", "FR-AUTH-01"),
    ("- NFR-SEC-2: Passwords shall be hashed", "NFR-SEC-2"),
    ("US001 Admin Manage system roles", "US001"),          # known prefix + 3 digits
    ("REQ1: The functional requirements of preprocessing", None),   # template label, not unique
    ("UTF-8 encoding shall be used", None),
])
def test_word_segment_and_compact_ids(text, rid):
    assert leading_requirement_id(text) == rid


def test_generic_skipped_section_does_not_hide_its_subsections():
    segs, _ = segments_of(
        "2 System Overview\n"
        "The system is a clinic platform.\n"
        "2.3 Future Enhancements\n"
        "Telemedicine module.\n"
        "2.4 User Stories\n"
        "US001 Admin Manage system roles so that I can control permissions.\n"
        "8 Appendix: API Endpoints\n"
        "8.1 Auth\n"
        "POST /api/auth/login/ authenticates a user.\n"
    )
    assert [s.requirement_id for s in segs] == ["US001"]


def test_repeated_ids_merge_acceptance_criteria_and_drop_code_maps():
    segs, report = segments_of(
        "3 Requirements Specification\n"
        "FR-1 Secure Auth Authentication using system credentials.\n"
        "FR-2 Conflict Check Rejects double booking.\n"
        "3.1 Acceptance Criteria\n"
        "FR-1: Users can register and log in; passwords are hashed with Argon2.\n"
        "4.2 Phases\n"
        "FR-1 Secure Auth accounts/models.py accounts/tests.py\n"
    )
    by_id = {s.requirement_id: s for s in segs}
    assert list(by_id) == ["FR-1", "FR-2"]
    assert "Argon2" in by_id["FR-1"].text and "models.py" not in by_id["FR-1"].text
    assert [r["action"].split()[0] for r in report.repeated_ids] == ["merged", "dropped:"]


def test_reused_template_ids_are_renamed_not_merged():
    segs, report = segments_of(
        "4.1 Car availability\n"
        "REQ-1: The customer can ask whether a car is available.\n"
        "4.2 Waiting list\n"
        "REQ-1: The customer can join a waiting list.\n"
    )
    assert [s.requirement_id for s in segs] == ["REQ-1", "REQ-1-2"]


def test_traceability_matrix_is_skipped_even_though_it_mentions_requirements():
    assert is_skip_section("5 Requirements Traceability Matrix (RTM)")
    assert is_skip_section("9. Verification & Acceptance Criteria")
    assert is_skip_section("4 Project Plan") and is_skip_section("6 Tools and Technologies")
    assert not is_skip_section("3.2 Email Verification")


def test_use_case_fields_are_grouped_under_the_use_case_title():
    segs, _ = segments_of(
        "4.1.3 View\n"
        "medical history\n"
        "Actors:\n"
        "- Patient\n"
        "Preconditions:\n"
        "- The patient is logged in.\n"
        "Postconditions:\n"
        "- The patient's history is shown.\n"
        "4.1.4 Logout\n"
    )
    assert len(segs) == 1
    assert segs[0].text.startswith("Use case: View medical history")
    assert "Postconditions:" in segs[0].text and "- Patient" in segs[0].text


def test_markdown_code_blocks_are_skipped():
    segs, report = segments_of(
        "## 6. Architecture\n"
        "```\n[User] --> [Agent] shall call tools\n```\n"
        "FR-1: The system shall log in users.\n"
    )
    assert [s.requirement_id for s in segs] == ["FR-1"] and len(report.code_blocks) == 1


def test_table_cells_are_not_headings_and_pdf_text_is_repaired():
    pages = [{"page": 1, "text": "FR-1 Secure Auth Authentication using system cre-\n"
                                 "dentials; passwords hashed.\n"
                                 "1 Critical (5%)\n"
                                 "Use case: m e d i c i n e s prescribed"}]
    blocks = blocks_from_pdf({"pages": pages})
    assert all(b.kind != "heading" for b in blocks)
    text = " ".join(b.text for b in blocks)
    assert "credentials;" in text and "medicines prescribed" in text
