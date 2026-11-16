from pathlib import Path
from typing import Dict, List

from docx import Document

from processors.segmenter import block_to_dict, blocks_from_docx


class DOCXParser:
    """
    Extracts the structure of a DOCX document in reading order: headings,
    paragraphs, list items (Word numbering or list styles) and tables.

    `blocks` keeps that structure for the segmenter, so a requirement keeps its
    bullets and tables.  `paragraphs` is a flat view kept for previews and
    backwards compatibility.
    """

    def parse(self, file_path: str) -> Dict:
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"DOCX not found: {file_path}")

        if path.suffix.lower() != ".docx":
            raise ValueError("Input file must be a DOCX document")

        blocks = blocks_from_docx(Document(str(path)))

        paragraphs: List[Dict] = []
        for block in blocks:
            if block.kind == "table":
                for row_index, row in enumerate(block.rows, start=1):
                    text = " | ".join(cell for cell in row if cell)
                    if text:
                        paragraphs.append({"paragraph": None, "text": text, "style": "Table Row",
                                           "table": block.location.get("table"), "row": row_index})
            else:
                paragraphs.append({"paragraph": block.location.get("paragraph"), "text": block.text,
                                   "style": block.location.get("style", "")})

        return {
            "file_name": path.name,
            "file_path": str(path),
            "paragraph_count": len(paragraphs),
            "paragraphs": paragraphs,
            "blocks": [block_to_dict(block) for block in blocks],
        }
