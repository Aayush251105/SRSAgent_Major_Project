from pathlib import Path
from typing import Any, Dict


class InputAdapter:
    """
    Detects the incoming SRS format and normalizes it into a common
    representation for the downstream requirement extraction pipeline.
    """

    SUPPORTED_FILE_TYPES = {
        ".pdf": "pdf",
        ".docx": "docx",
    }

    SUPPORTED_DATA_TYPES = {
        dict: "json",
        list: "json",
        str: "text",
    }

    def detect(self, input_data: Any) -> str:
        """Determine whether the input is a file, JSON object, or plain text."""

        if isinstance(input_data, (dict, list)):
            return "json"

        if isinstance(input_data, str):
            path = Path(input_data)

            if path.exists() and path.is_file():
                extension = path.suffix.lower()

                if extension in self.SUPPORTED_FILE_TYPES:
                    return self.SUPPORTED_FILE_TYPES[extension]

                raise ValueError(f"Unsupported file type: {extension}")

            return "text"

        raise ValueError(
            f"Unsupported input type: {type(input_data).__name__}"
        )

    def adapt(self, input_data: Any) -> Dict[str, Any]:
        """
        Convert detected input into a common structure.

        Actual PDF/DOCX parsing is handled by dedicated parsers.
        """

        input_type = self.detect(input_data)

        return {
            "type": input_type,
            "data": input_data,
        }