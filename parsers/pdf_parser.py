from pathlib import Path
from typing import Dict, List

from pypdf import PdfReader


class PDFParser:
    """
    Extracts text from PDF documents while preserving page boundaries
    for requirement source traceability.
    """

    def parse(self, file_path: str) -> Dict:
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {file_path}")

        if path.suffix.lower() != ".pdf":
            raise ValueError("Input file must be a PDF")

        reader = PdfReader(str(path))

        if reader.is_encrypted:
            raise ValueError("Encrypted PDFs are not supported")

        pages: List[Dict] = []

        for page_number, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""

            pages.append({
                "page": page_number,
                "text": text.strip()
            })

        return {
            "file_name": path.name,
            "file_path": str(path),
            "page_count": len(pages),
            "pages": pages,
            "text": "\n".join(page["text"] for page in pages),
        }
