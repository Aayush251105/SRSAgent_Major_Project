# SRSAgent V1

Extract requirement records from plain text, selectable-text PDFs, and DOCX files.
The program returns a JSON array in source order and assigns IDs as `REQ-001`,
`REQ-002`, and so on.

## Setup

```powershell
cd SRSAgent
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

The default provider is Ollama. Start Ollama and pull the configured model
(`ollama pull llama3.1`), or edit `.env` to use Grok and set `XAI_API_KEY`.

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
