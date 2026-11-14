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
