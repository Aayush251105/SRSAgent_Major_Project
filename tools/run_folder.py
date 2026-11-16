"""
Run the SRS Agent on every SRS document in a folder and save the results there.

Standalone: only the agent's own pipeline runs (parse -> detect -> judge ->
extract).  Nothing is written to any database.

    .venv\\Scripts\\python.exe tools\\run_folder.py ..\\SRSAgent_test            # -> ..\\SRSAgent_test\\results
    .venv\\Scripts\\python.exe tools\\run_folder.py ..\\SRSAgent_test results_v2
    .venv\\Scripts\\python.exe tools\\run_folder.py ..\\SRSAgent_test results_v2 "a.pdf" "b.md"   # only these

When file names are given, only those documents run, and their entries are
merged into the output folder's existing summary.json (other entries are kept).

Models come from the usual environment variables (LLM_MODEL, JUDGE_MODEL,
OLLAMA_HOST).  For each document it writes <name>_requirements.json and
<name>_extraction_report.json; summary.json holds counts and timings.
"""

import json
import re
import sys
import time
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AGENT_DIR))

import app  # noqa: E402

SUFFIXES = {".pdf", ".docx", ".md", ".markdown", ".txt"}


def run(folder: Path, out_name: str = "results", only: list = None) -> list:
    out_dir = folder / out_name
    out_dir.mkdir(exist_ok=True)
    files = all_files = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in SUFFIXES)
    if only:
        missing = [name for name in only if not (folder / name).is_file()]
        if missing:
            sys.exit(f"not found in {folder}: {missing}")
        files = [p for p in files if p.name in set(only)]
    summary = []
    for path in files:
        print(f"\n=== {path.name}", flush=True)
        progress = app.TerminalProgress()
        report: dict = {}
        started = time.time()
        try:
            requirements = app.main(str(path), progress_callback=progress, report=report)
            progress.finish(len(requirements))
            error = None
        except Exception as exc:          # keep going with the next document
            requirements, error = [], f"{type(exc).__name__}: {exc}"
            print("FAILED:", error, flush=True)
        seconds = round(time.time() - started, 1)

        stem = re.sub(r"[^A-Za-z0-9._-]+", "_", path.stem).strip("_")
        if sum(1 for p in all_files if p.stem == path.stem) > 1:   # SRS.md and SRS.pdf
            stem += "_" + path.suffix.lstrip(".").lower()
        data = [r.model_dump(mode="json") for r in requirements]
        (out_dir / f"{stem}_requirements.json").write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        report.update(candidate_review=progress.review_items, error=error, seconds=seconds)
        (out_dir / f"{stem}_extraction_report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")

        segmentation = report.get("segmentation") or {}
        types: dict = {}
        for r in data:
            types[r.get("type")] = types.get(r.get("type"), 0) + 1
        summary.append({
            "file": path.name, "seconds": seconds, "error": error,
            "requirements": len(data),
            "source_ids": sum(1 for r in data if r.get("id_source") == "source"),
            "generated_ids": sum(1 for r in data if r.get("id_source") == "generated"),
            "with_parent": sum(1 for r in data if r.get("parent_requirement_id")),
            "types": types,
            "counts": report.get("counts"),
            "skipped_sections": len(segmentation.get("skipped_sections") or []),
            "toc_lines": len(segmentation.get("toc_lines") or []),
            "duplicates_dropped": len(segmentation.get("duplicates") or []),
            "list_intros_dropped": sum(1 for w in segmentation.get("warnings") or [] if w.get("dropped")),
            "review_items": len(progress.review_items),
            "extraction_failures": len(report.get("extraction_failures") or []),
        })
        print(json.dumps(summary[-1], indent=1), flush=True)

    summary_path = out_dir / "summary.json"
    if only and summary_path.is_file():          # merge: keep the entries of documents not re-run
        done = {entry["file"] for entry in summary}
        previous = json.loads(summary_path.read_text(encoding="utf-8"))
        summary = [entry for entry in previous if entry.get("file") not in done] + summary
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print("\nsaved to", out_dir)
    return summary


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    run(Path(sys.argv[1]).resolve(), sys.argv[2] if len(sys.argv) > 2 else "results", sys.argv[3:] or None)
