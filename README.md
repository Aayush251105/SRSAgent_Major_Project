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

## V1 boundaries

- PDF text must be selectable; scanned-PDF OCR is not included.
- DOCX paragraphs and table cells are read.
- Candidate detection relies on common requirement wording (for example,
  “shall”, “must”, “should”, and “is required”). Review output for documents
  that use less explicit language.
- IDs are assigned after extraction in encounter order. The `source` object
  preserves the filename and page, paragraph, or table-cell location when
  available.
