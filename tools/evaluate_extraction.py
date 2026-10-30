"""
Compare SRS Agent output with a gold-standard mapping (format v2).

    python tools/evaluate_extraction.py output/SRS_Library_Management_System_requirements.txt \
        ../library_traceability_dataset/gold_standard/gold_standard_mapping.json

Reports:
  id_recall        gold requirement IDs found with id_source = "source"
  spurious         extracted requirements whose ID is not in the gold
  complete         gold requirements whose words/numbers all appear in the
                   extracted raw_text (lists and tables included)
  empty fields     requirements with an empty normalized_text or retrieval_text
  type agreement   FR -> functional, NFR -> non-functional
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

_TOKEN = re.compile(r"[a-z]+|\d+(?:\.\d+)?")


def tokens(text: str) -> List[str]:
    # List numbering ("1. ", "2) ") is formatting: Word auto-numbering is not
    # part of the paragraph text, so it must not count as missing content.
    text = re.sub(r"(?m)^\s*\d+[.)]\s+", "", text)
    text = text.lower().replace("’", "'")
    return _TOKEN.findall(re.sub(r"\b(?:n?fr|req)-\d+(?:\.\d+)*\b", " ", text))


def coverage(gold_text: str, extracted: str) -> float:
    gold = tokens(gold_text)
    if not gold:
        return 1.0
    have = set(tokens(extracted))
    return sum(t in have for t in gold) / len(gold)


def evaluate(requirements: List[Dict[str, Any]], gold: Dict[str, Any],
             complete_threshold: float = 0.95) -> Dict[str, Any]:
    by_id = {r["requirement_id"]: r for r in requirements}
    gold_reqs = gold["requirements"]
    gold_ids = [g["requirement_id"] for g in gold_reqs]
    found = [i for i in gold_ids if i in by_id and by_id[i].get("id_source") == "source"]
    incomplete = {}
    for g in gold_reqs:
        r = by_id.get(g["requirement_id"])
        if r is None:
            continue
        cov = coverage(g["text"], r["raw_text"])
        if cov < complete_threshold:
            incomplete[g["requirement_id"]] = round(cov, 3)
    expected_type = {i: ("non-functional" if i.upper().startswith("NFR") else "functional") for i in gold_ids}
    type_mismatch = [i for i in found if by_id[i].get("type") != expected_type[i]]
    return {
        "gold_requirements": len(gold_ids),
        "extracted_requirements": len(requirements),
        "id_recall": round(len(found) / len(gold_ids), 4) if gold_ids else None,
        "missing_ids": [i for i in gold_ids if i not in found],
        "spurious": [{"requirement_id": r["requirement_id"], "text": r["raw_text"][:120]}
                     for r in requirements if r["requirement_id"] not in set(gold_ids)],
        "complete": len(found) - len(incomplete),
        "incomplete": incomplete,
        "empty_normalized_text": [r["requirement_id"] for r in requirements if not r.get("normalized_text", "").strip()],
        "empty_retrieval_text": [r["requirement_id"] for r in requirements if not r.get("retrieval_text", "").strip()],
        "type_mismatch": type_mismatch,
        "with_parent": sum(1 for r in requirements if r.get("parent_requirement_id")),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("output", help="SRS Agent output (JSON array, e.g. output/<name>_requirements.txt)")
    ap.add_argument("gold", help="Gold mapping v2 JSON")
    args = ap.parse_args(argv)
    requirements = json.loads(Path(args.output).read_text(encoding="utf-8"))
    gold = json.loads(Path(args.gold).read_text(encoding="utf-8"))
    report = evaluate(requirements, gold)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    ok = report["id_recall"] == 1.0 and not report["spurious"] and not report["incomplete"]
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
