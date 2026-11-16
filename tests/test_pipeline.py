"""Detector → judge → extraction, with a fake LLM provider."""

import app
from agents.srs_agent import SRSAgent
from parsers.docx_parser import DOCXParser
from processors.requirement_detector import RequirementDetector
from tests.conftest import BASIC_DOCX, LIBRARY_DOC_ORDER, LIBRARY_DOCX, FakeProvider


def test_detector_on_library_docx():
    detector = RequirementDetector()
    candidates = detector.detect(DOCXParser().parse(str(LIBRARY_DOCX)), "docx")
    labelled = [c for c in candidates if c.get("source_requirement_id")]
    assert [c["source_requirement_id"] for c in labelled] == LIBRARY_DOC_ORDER
    assert all(c["detection_confidence"] == "high" for c in labelled)
    fr12 = next(c for c in labelled if c["source_requirement_id"] == "FR-012")
    assert fr12["structure"]["list_items"] == 3
    assert fr12["source"]["section"].startswith("3.2")
    assert detector.last_report.skipped_sections


def test_detector_filters_front_matter_and_keeps_parents():
    candidates = RequirementDetector().detect(DOCXParser().parse(str(BASIC_DOCX)), "docx")
    texts = [c["text"] for c in candidates]
    assert not any(t.startswith(("SOFTWARE REQUIREMENTS", "Version 1.0", "SRS Document")) for t in texts)
    child = next(c for c in candidates if c.get("source_requirement_id") == "FR-02.3")
    assert child["parent_requirement_id"] == "FR-02"


def _candidates():
    return RequirementDetector().detect(DOCXParser().parse(str(LIBRARY_DOCX)), "docx")


def test_extraction_keeps_full_text_ids_and_parents():
    candidates = [c for c in _candidates() if c.get("source_requirement_id") in ("FR-002", "FR-012")]
    reqs = SRSAgent(FakeProvider()).extract(candidates)
    by_id = {r.requirement_id: r for r in reqs}
    assert by_id["FR-002"].id_source == "source"
    assert "- the number of copies is less than 1;" in by_id["FR-002"].raw_text
    assert "- Membership type: staff; Borrowing limit: 10" in by_id["FR-012"].raw_text
    assert by_id["FR-012"].source.paragraph is not None


def test_empty_model_text_fields_are_filled():
    candidates = [c for c in _candidates() if c.get("source_requirement_id") == "FR-022"]
    req = SRSAgent(FakeProvider(empty_text=True)).extract(candidates)[0]
    assert req.normalized_text.startswith("Fine calculation The fine for a loan")
    assert "FR-022" not in req.normalized_text
    assert req.retrieval_text == "requirement do x thing"


def test_transient_failure_is_retried():
    candidates = [c for c in _candidates() if c.get("source_requirement_id") == "FR-001"]
    agent = SRSAgent(FakeProvider(fail=1))
    assert [r.requirement_id for r in agent.extract(candidates)] == ["FR-001"]
    assert agent.failures == []


def test_persistent_failure_is_reported_not_fatal():
    candidates = [c for c in _candidates() if c.get("source_requirement_id") in ("FR-001", "FR-003")]
    agent = SRSAgent(FakeProvider(fail=2))          # FR-001 fails twice, FR-003 succeeds
    reqs = agent.extract(candidates)
    assert [r.requirement_id for r in reqs] == ["FR-003"]
    assert agent.failures[0]["requirement_id"] == "FR-001" and "timed out" in agent.failures[0]["error"]


def test_generated_ids_never_collide_with_source_ids():
    text_candidates = RequirementDetector().detect_text(
        "The system shall export data.\n\nREQ-001: The system shall import data.")
    for c in text_candidates:
        c["input_kind"] = "text"
    reqs = SRSAgent(FakeProvider()).extract(text_candidates)
    ids = [r.requirement_id for r in reqs]
    assert "REQ-001" in ids and len(set(ids)) == len(ids)


def test_main_end_to_end_with_report(monkeypatch):
    monkeypatch.setattr(app, "create_provider", lambda config, model_override=None: FakeProvider())
    report = {}
    reqs = app.main(str(LIBRARY_DOCX), report=report)
    labelled = [r.requirement_id for r in reqs if r.id_source == "source"]
    assert labelled == LIBRARY_DOC_ORDER
    assert not any(r.requirement_id.startswith("REQ-") and "must be returned" in r.raw_text for r in reqs)
    assert report["counts"]["extracted"] == len(reqs) and report["extraction_failures"] == []
    assert any(s["heading"] == "1.3 Definitions" for s in report["segmentation"]["skipped_sections"])


def test_evaluation_tool_ignores_list_numbering_and_flags_gaps():
    from tools.evaluate_extraction import coverage, evaluate
    assert coverage("Steps:\n1. build the catalog;\n2. print the report.",
                    "Steps:\n- build the catalog;\n- print the report.") == 1.0
    gold = {"requirements": [{"requirement_id": "FR-1", "text": "The fine shall not exceed 20.00."}]}
    report = evaluate([{"requirement_id": "FR-1", "id_source": "source", "raw_text": "The fine shall",
                        "type": "functional", "normalized_text": "x", "retrieval_text": "y"},
                       {"requirement_id": "REQ-001", "id_source": "generated", "raw_text": "Glossary row",
                        "type": "functional", "normalized_text": "", "retrieval_text": "y"}], gold)
    assert report["incomplete"] == {"FR-1": 0.5} and report["spurious"][0]["requirement_id"] == "REQ-001"
    assert report["empty_normalized_text"] == ["REQ-001"]
