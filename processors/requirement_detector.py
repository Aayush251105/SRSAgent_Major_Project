import re
from typing import Dict, List


class RequirementDetector:
    """
    Identifies text that is likely to represent a software requirement.

    This stage only detects candidates. Semantic extraction and normalization
    are handled by the SRS Agent.
    """

    REQUIREMENT_PATTERNS = [
        r"\bshall\b",
        r"\bmust\b",
        r"\bshould\b",
        r"\brequired to\b",
        r"\bneeds to\b",
        r"\bis required\b",
        r"\bwill\b",
    ]

    def is_requirement(self, text: str) -> bool:
        """Check whether a text segment contains common requirement language."""

        text = text.strip()

        if not text:
            return False

        return any(
            re.search(pattern, text, re.IGNORECASE)
            for pattern in self.REQUIREMENT_PATTERNS
        )

    def detect(
        self,
        document: Dict,
        source_type: str
    ) -> List[Dict]:
        """
        Extract candidate requirements while preserving their source location.
        """

        candidates = []

        if source_type == "pdf":
            for page in document["pages"]:
                segments = self._split_text(page["text"])

                for segment in segments:
                    if self.is_requirement(segment):
                        candidates.append({
                            "text": segment,
                            "source": {
                                "file_name": document["file_name"],
                                "page": page["page"],
                            }
                        })

        elif source_type == "docx":
            for paragraph in document["paragraphs"]:
                for segment in self._split_text(paragraph["text"]):
                    if self.is_requirement(segment):
                        source = {
                            "file_name": document["file_name"],
                            "paragraph": paragraph.get("paragraph"),
                        }
                        for key in ("table", "row", "column"):
                            if key in paragraph:
                                source[key] = paragraph[key]
                        candidates.append({"text": segment, "source": source})

        else:
            raise ValueError(
                f"Unsupported document source type: {source_type}"
            )

        return candidates

    @staticmethod
    def _split_text(text: str) -> List[str]:
        """Split extracted text into lines and common list-item segments."""
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        segments: List[str] = []
        for line in lines:
            pieces = re.split(
                r"(?<=[.;])\s+(?=(?:REQ[- ]?\d+|\d+(?:\.\d+)*[.)]?|[-*•])\s+)",
                line,
            )
            segments.extend(piece.strip() for piece in pieces if piece.strip())
        return segments

    def detect_text(self, text: str) -> List[Dict]:
        """Detect requirements in plain text using the same rules as files."""
        candidates = []
        for segment in self._split_text(text):
            if self.is_requirement(segment):
                candidates.append({"text": segment, "source": {}})
        return candidates
