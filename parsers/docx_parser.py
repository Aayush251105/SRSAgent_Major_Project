from pathlib import Path
import re
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

    REQUIREMENT_ID_PATTERN = re.compile(
        r"^\s*\(?([A-Za-z][A-Za-z0-9_-]*[-_]\d+(?:[.-]\d+)*)\)?\s*[:.)-]?\s*$"
    )

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
                    cell_texts = [
                        " ".join(
                            item.text.strip()
                            for item in cell.paragraphs
                            if item.text.strip()
                        )
                        for cell in row.cells
                    ]
                    row_requirement_id = next(
                        (
                            match.group(1)
                            for cell_text in cell_texts
                            if (match := self.REQUIREMENT_ID_PATTERN.match(cell_text))
                        ),
                        None,
                    )
                    for column_index, cell in enumerate(row.cells, start=1):
                        text = cell_texts[column_index - 1]
                        if text:
                            paragraphs.append({
                                "paragraph": None,
                                "text": text,
                                "style": "Table Cell",
                                "table": table_index,
                                "row": row_index,
                                "column": column_index,
                                "source_requirement_id": row_requirement_id,
                            })

        return {
            "file_name": path.name,
            "file_path": str(path),
            "paragraph_count": len(paragraphs),
            "paragraphs": paragraphs,
        }
