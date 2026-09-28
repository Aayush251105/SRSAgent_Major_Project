from pathlib import Path
from typing import Dict, List

from docx import Document


class DOCXParser:
    """
    Extracts paragraphs from DOCX documents while preserving their
    order and basic heading structure for later requirement traceability.
    """

    def parse(self, file_path: str) -> Dict:
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"DOCX not found: {file_path}")

        if path.suffix.lower() != ".docx":
            raise ValueError("Input file must be a DOCX document")

        document = Document(str(path))

        paragraphs: List[Dict] = []

        for index, paragraph in enumerate(document.paragraphs, start=1):
            text = paragraph.text.strip()

            if not text:
                continue

            paragraphs.append({
                "paragraph": index,
                "text": text,
                "style": paragraph.style.name
            })

        return {
            "file_name": path.name,
            "file_path": str(path),
            "paragraph_count": len(paragraphs),
            "paragraphs": paragraphs,
        }