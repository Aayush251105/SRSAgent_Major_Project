# SRSAgent V1

Extract requirement records from plain text, selectable-text PDFs, and DOCX files.
The program returns a JSON array in source order and assigns IDs as `REQ-001`,
`REQ-002`, and so on.

If a document labels a requirement with an ID such as `FR-01.2` or `NFR-02.1`,
that source ID is retained as `requirement_id` and `id_source` is set to `source`.
Unlabeled requirements receive generated `REQ-...` IDs and
`id_source: "generated"`.

Requirement classification uses `type` with exactly three base values:
`functional`, `non-functional`, or `other`. `subtype` carries the more specific
category, for example `type: "functional", subtype: "interface"` (read as
“functional - interface”). FR and NFR ID prefixes determine the base type for
those labeled requirements. For literal plain-text input, `type` is `other` and
`subtype` records the specific category inferred from the sentence.

The detector keeps each DOCX paragraph or table cell as one candidate, preserving
its complete raw text. For plain text and PDF, blank lines define paragraphs;
multiple adjacent lines stay together unless they carry explicit requirement IDs.
The detector recognizes common functional wording and non-functional quality
attributes such as response time, availability, reliability, security,
accessibility, and measurable limits.

Candidates with explicit IDs or strong requirement signals use a fast rule-based
approval path and go directly to JSON extraction. Ambiguous candidates go through
the LLM judge in batches (up to twenty, subject to a prompt-size limit). Only
judge-approved items reach extraction. Uncertain items, including missing
decisions after a judge error, are excluded and saved to
`<input>_candidate_review.txt`. Obvious titles, headings, and document metadata
are filtered where they can be identified from text or DOCX style.

Outputs include heuristic `detection_confidence` / `detection_reason` and the
LLM's `candidate_decision`, `candidate_confidence`, and `candidate_reason`.
`review_required` is true for uncertain candidates or any non-high-confidence
judgment. The candidate decision is included in the final record for traceability.

## Setup

```powershell
cd SRSAgent
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

The default provider is Ollama. Pull both configured models:

```powershell
ollama pull llama3.1
ollama pull qwen2.5:3b
```

`LLM_MODEL` generates the final JSON; `JUDGE_MODEL` reviews ambiguous
candidates. If the smaller judge model is unavailable or errors, the pipeline
falls back to `LLM_MODEL`. Set `JUDGE_MODEL` in `.env` to another installed
Ollama model. With Grok, the configured Grok model handles both roles.

## Run

```powershell
python app.py "C:\path\to\requirements.pdf"
python app.py "C:\path\to\requirements.docx"
python app.py "The system shall allow users to reset their password."
```

The Python entry point is `main(input_data)` in `app.py`; it accepts a literal
string or a path to a `.pdf`/`.docx` file and returns Pydantic `Requirement`
objects. JSON objects/lists are intentionally rejected in V1 because there is
no input JSON contract yet.

The CLI writes progress to stderr and the final JSON array to stdout. It also
saves that complete JSON-formatted output as a `.txt` file under `output/`
(`Basic_SRS_Document_requirements.txt` for the example DOCX). Each run replaces
the prior output for the same input. It shows
the parsed input, detected candidate text, an updating elapsed timer/progress
bar during each model call, and each completed requirement as it is generated.
An ETA is estimated after the first requirement completes. To save only the
final JSON to a file while still seeing progress in the terminal, use:

```powershell
python app.py "C:\path\to\requirements.pdf" > output.json
```

## Check Ollama GPU/CPU use

While the agent is generating a requirement, open another PowerShell window and
run:

```powershell
ollama ps
```

Check the `PROCESSOR` column: `100% GPU` means GPU inference, `100% CPU` means
CPU inference, and a CPU/GPU split means some model layers are running on each.
The model may unload shortly after generation finishes, so run this while the
progress bar is active. On NVIDIA systems, `nvidia-smi -l 1` can also show GPU
utilization and memory use.

## V1 boundaries

- PDF text must be selectable; scanned-PDF OCR is not included.
- DOCX paragraphs and table cells are read.
- Candidate detection relies on common requirement wording (for example,
  “shall”, “must”, “should”, and “is required”). Review output for documents
  that use less explicit language.
- IDs are assigned after extraction in encounter order. The `source` object
  preserves the filename and page, paragraph, or table-cell location when
  available.
