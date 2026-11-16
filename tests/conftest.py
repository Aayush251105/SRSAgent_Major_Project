"""Shared fixtures for the SRS Agent tests (no LLM, no network)."""

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FIXTURES = Path(__file__).parent / "fixtures"
LIBRARY_DOCX = FIXTURES / "SRS_Library_Management_System.docx"
LIBRARY_PDF = FIXTURES / "SRS_Library_Management_System.pdf"
LIBRARY_MD = FIXTURES / "SRS_Library_Management_System.md"
LIBRARY_GOLD = FIXTURES / "library_gold_v2.json"
BASIC_DOCX = ROOT / "input" / "Basic_SRS_Document.docx"

# The 39 requirement IDs of the library SRS v1.1, in document order.
LIBRARY_IDS = [r["requirement_id"] for r in json.loads(LIBRARY_GOLD.read_text(encoding="utf-8"))["requirements"]]
LIBRARY_DOC_ORDER = [
    "FR-001", "FR-002", "FR-003", "FR-004", "FR-005", "FR-006", "FR-007", "FR-032", "FR-036",
    "FR-008", "FR-009", "FR-010", "FR-011", "FR-012", "FR-013", "FR-014", "FR-015", "FR-033",
    "FR-035", "FR-016", "FR-017", "FR-018", "FR-019", "FR-020", "FR-021", "FR-031", "FR-034",
    "FR-022", "FR-023", "FR-024", "FR-025", "FR-026", "FR-027", "FR-028", "FR-029", "FR-030",
    "NFR-001", "NFR-002", "NFR-003",
]


class FakeProvider:
    """
    Stands in for an LLM provider.  Requirement extraction returns a minimal
    valid record; the candidate judge keeps every candidate with high
    confidence.  `fail` makes the next N calls raise.
    """

    def __init__(self, fail: int = 0, empty_text: bool = False):
        self.fail = fail
        self.empty_text = empty_text
        self.calls = 0

    def generate_structured(self, prompt, schema):
        self.calls += 1
        if self.fail > 0:
            self.fail -= 1
            raise RuntimeError("model timed out")
        if schema.__name__ == "CandidateJudgmentBatch":
            ids = re.findall(r'"candidate_id": "(C-\d+)"', prompt)
            return {"judgments": [{"candidate_id": i, "decision": "keep", "confidence": "high",
                                   "reason": "clear requirement"} for i in ids]}
        empty = "" if self.empty_text else None
        return {
            "raw_text": "ignored", "normalized_text": empty if empty is not None else "The system does X.",
            "type": "functional", "subtype": "general", "title": "Requirement",
            "actor": [], "actions": ["do x"], "entities": ["thing"], "inputs": [], "outputs": [],
            "preconditions": [], "postconditions": [], "conditions": [], "constraints": [],
            "error_conditions": [], "domain_terms": [], "synonyms": [], "sub_requirements": [],
            "retrieval_text": empty if empty is not None else "do x thing",
        }


@pytest.fixture()
def fake_provider():
    return FakeProvider()


def make_docx(tmp_path, build) -> str:
    """Create a .docx with python-docx; `build(doc)` adds the content."""
    from docx import Document
    doc = Document()
    build(doc)
    path = tmp_path / "test.docx"
    doc.save(str(path))
    return str(path)
