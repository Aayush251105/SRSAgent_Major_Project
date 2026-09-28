from pathlib import Path
from typing import Dict, List

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph


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
        paragraph_index = 0
        table_index = 0

        # Walk body blocks in document order so generated requirement IDs
        # follow the order users see in Word.
        for child in document.element.body.iterchildren():
            if child.tag == qn("w:p"):
                paragraph_index += 1
                paragraph = Paragraph(child, document)
                text = paragraph.text.strip()
                if text:
                    paragraphs.append({
                        "paragraph": paragraph_index,
                        "text": text,
                        "style": paragraph.style.name,
                    })
            elif child.tag == qn("w:tbl"):
                table_index += 1
                table = Table(child, document)
                for row_index, row in enumerate(table.rows, start=1):
                    for column_index, cell in enumerate(row.cells, start=1):
                        text = " ".join(
                            item.text.strip()
                            for item in cell.paragraphs
                            if item.text.strip()
                        )
                        if text:
                            paragraphs.append({
                                "paragraph": None,
                                "text": text,
                                "style": "Table Cell",
                                "table": table_index,
                                "row": row_index,
                                "column": column_index,
                            })

        return {
            "file_name": path.name,
            "file_path": str(path),
            "paragraph_count": len(paragraphs),
            "paragraphs": paragraphs,
        }
