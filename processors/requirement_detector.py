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

    REQUIREMENT_SIGNAL_PATTERNS = {
        "high": {
            "explicit obligation wording": (
                r"\bshall\b", r"\bmust\b", r"\bshould\b",
                r"\bneeds? to\b", r"\bhas to\b", r"\bhave to\b",
                r"\bis required to\b", r"\bare required to\b",
                r"\bmust not\b", r"\bshall not\b",
            ),
        },
        "medium": {
            "capability or expected behavior wording": (
                r"\bwill\b", r"\bcan\b", r"\bmay\b",
                r"\bis expected to\b", r"\bare expected to\b",
                r"\bis able to\b", r"\bare able to\b",
            ),
        },
    }

    ACTION_VERBS = (
        "allow", "enable", "provide", "display", "show", "send", "validate",
        "store", "retrieve", "create", "update", "delete", "modify", "manage",
        "access", "authenticate", "authorize", "support", "ensure", "maintain",
        "prevent", "reject", "accept", "return", "generate", "record", "submit",
        "search", "filter", "export", "import", "calculate", "notify", "respond",
        "operate", "load", "process", "log", "encrypt", "run", "communicate",
        "use", "remain", "include", "contain", "keep", "identify", "select",
        "view", "download", "upload", "connect", "transmit", "delete", "reset",
        "schedule", "cancel", "configure", "save", "verify", "check", "track",
    )

    SOURCE_ID_PATTERN = re.compile(
        r"^\s*(?:[-*•]\s*)?\(?[A-Za-z][A-Za-z0-9_-]*[-_]\d+(?:[.-]\d+)*\)?(?=\s|:|\.|\))"
    )

    DOCUMENT_METADATA_PATTERNS = (
        r"^software requirements specification\b",
        r"^srs document\b",
        r"^(?:document )?(?:version|revision|date|author|prepared by|approved by|status)\s*[:|#-]",
        r"^(?:version|revision)\s+\d+(?:\.\d+)*\b",
        r"^\d{1,2}[/-]\d{1,2}[/-](?:\d{2}|\d{4})\s*$",
        r"^(?:table of contents|contents|revision history|document history)$",
    )

    NON_FUNCTIONAL_PATTERNS = (
        r"\bperformance\b", r"\bresponse time\b", r"\blatency\b",
        r"\bthroughput\b", r"\bscalab(?:le|ility)\b", r"\bsecurity\b",
        r"\bavailability\b", r"\buptime\b", r"\breliability\b",
        r"\busability\b", r"\baccessibility\b", r"\bmaintainability\b",
        r"\bportability\b", r"\bcompatibility\b", r"\bprivacy\b",
        r"\bconfidentiality\b", r"\binteroperability\b", r"\bfault tolerance\b",
        r"\bdata integrity\b", r"\bauditability\b", r"\bobservability\b",
        r"\befficiency\b", r"\befficient\b", r"\bprocessing overhead\b",
        r"\bavoid unnecessary processing\b", r"\bresource utilization\b",
        r"\bcapacity\b", r"\bconcurrent users\b", r"\bmemory usage\b",
        r"\bresource usage\b", r"\bCPU usage\b",
        r"\b\d+(?:\.\d+)?\s*(?:ms|milliseconds?|seconds?|minutes?|hours?)\b",
        r"\b\d+\s*%\b", r"\b(?:recover|recovery) within\b",
    )

    def is_requirement(self, text: str) -> bool:
        """Return whether text is a likely requirement candidate."""
        return self.assess(text) is not None

    @classmethod
    def assess(cls, text: str):
        """Return confidence and evidence, or None when text is not a candidate."""
        cleaned = cls._strip_list_prefix(text).strip()
        if not cleaned:
            return None

        source_id_match = cls.SOURCE_ID_PATTERN.match(cleaned)
        if source_id_match and not cleaned[source_id_match.end():].strip(" :.)-"):
            return None
        if source_id_match:
            return "high", "contains a source requirement ID"

        for patterns in cls.REQUIREMENT_SIGNAL_PATTERNS["high"].values():
            for pattern in patterns:
                match = re.search(pattern, cleaned, re.IGNORECASE)
                if match:
                    return "high", f"explicit obligation wording: {match.group(0)}"

        measurable_target = re.search(
            r"\b\d+(?:\.\d+)?\s*(?:(?:ms|milliseconds?|seconds?|minutes?|hours?)\b|%)",
            cleaned,
            re.IGNORECASE,
        )
        if measurable_target:
            return "high", f"contains a measurable target: {measurable_target.group(0)}"

        if any(re.search(pattern, cleaned, re.IGNORECASE) for pattern in cls.NON_FUNCTIONAL_PATTERNS):
            return "medium", "contains a non-functional quality attribute or measurable target"

        for confidence, signal_groups in cls.REQUIREMENT_SIGNAL_PATTERNS.items():
            for description, patterns in signal_groups.items():
                for pattern in patterns:
                    match = re.search(pattern, cleaned, re.IGNORECASE)
                    if match:
                        return confidence, f"{description}: {match.group(0)}"

        verb_pattern = r"(?:" + "|".join(cls.ACTION_VERBS) + r")"
        verb_pattern += r"(?:s|es|ed|ing)?"
        subject_pattern = (
            r"^(?:(?:the\s+)?(?:system|application|software|service|user|users|"
            r"administrator|administrators|admin|admins|customer|customers|client|"
            r"server|interface|form|data|records?|database|API|passwords?)\b)"
            r"(?:\s+\w+){0,3}\s+"
        )
        if re.search(subject_pattern + verb_pattern + r"\b", cleaned, re.IGNORECASE):
            return "medium", "starts with an actor or system and an action"

        if re.match(verb_pattern + r"\b", cleaned, re.IGNORECASE):
            return "medium", "starts with an actionable instruction"

        return None

    @staticmethod
    def _strip_list_prefix(text: str) -> str:
        return re.sub(r"^\s*(?:(?:[-*•])\s+|\d+(?:\.\d+)*[.)]\s+)", "", text)

    @classmethod
    def _candidate(cls, text: str, source: Dict) -> Dict | None:
        source_requirement_id = source.get("source_requirement_id")
        if source_requirement_id and re.fullmatch(
            rf"\s*(?:[-*•]\s*)?{re.escape(source_requirement_id)}\s*[:.)-]?\s*",
            text,
            re.IGNORECASE,
        ):
            return None
        # Keep the whole source paragraph/table cell as raw text. A visual line
        # break is not a reliable boundary between requirements.
        original_text = text.strip()
        text = " ".join(text.split())
        assessment = cls.assess(text)
        explicit_metadata = any(
            re.search(pattern, text, re.IGNORECASE)
            for pattern in cls.DOCUMENT_METADATA_PATTERNS
        )
        if explicit_metadata or (
            cls._is_document_metadata(text, source)
            and (assessment is None or assessment[0] != "high")
        ):
            return None
        if assessment is None and source_requirement_id and len(text.split()) >= 4:
            assessment = ("medium", "text is associated with an explicitly labeled requirement row")
        if assessment is None and re.match(
            r"^\s*(?:[-*•]\s+|\d+(?:\.\d+)*[.)]\s+)", text
        ):
            cleaned = cls._strip_list_prefix(text).strip()
            if len(cleaned.split()) >= 4 and not cleaned.endswith(":"):
                assessment = ("low", "numbered or bulleted item; included for review")
        if assessment is None:
            cleaned = cls._strip_list_prefix(text).strip()
            if len(cleaned.split()) >= 2 and not cleaned.endswith(":"):
                assessment = ("low", "no explicit requirement signal; sent to LLM judge")
        if assessment is None:
            return None
        confidence, reason = assessment
        candidate = {
            "text": original_text,
            "source": source,
            "detection_confidence": confidence,
            "detection_reason": reason,
        }
        if source_requirement_id:
            candidate["source_requirement_id"] = source_requirement_id
        candidate["requirement_class"] = cls._requirement_class(text, source_requirement_id)
        return candidate

    @classmethod
    def _requirement_class(cls, text: str, source_requirement_id: str | None = None) -> str:
        identifier = (source_requirement_id or "").upper()
        if not identifier:
            match = cls.SOURCE_ID_PATTERN.match(text)
            identifier = match.group(0).upper() if match else ""
        if identifier.startswith(("NFR", "NF", "NFRQ", "NONFUNC", "QUALITY")):
            return "non-functional"
        if identifier.startswith(("F-", "F_", "FR", "FREQ", "FUNC", "FUNCTIONAL")):
            return "functional"
        if any(re.search(pattern, text, re.IGNORECASE) for pattern in cls.NON_FUNCTIONAL_PATTERNS):
            return "non-functional"
        return "functional"

    @classmethod
    def _is_document_metadata(cls, text: str, source: Dict) -> bool:
        cleaned = cls._strip_list_prefix(text).strip()
        if any(re.search(pattern, cleaned, re.IGNORECASE) for pattern in cls.DOCUMENT_METADATA_PATTERNS):
            return True

        words = cleaned.split()
        style = str(source.get("style", "")).lower()
        heading_style = "heading" in style or style in {"title", "subtitle"}
        title_like = (
            (cleaned.isupper() or cleaned.istitle())
            and 1 <= len(words) <= 10
            and not re.search(r"\d{4,}", cleaned)
        )
        return heading_style or title_like

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
                    candidate = self._candidate(segment, {
                        "file_name": document["file_name"],
                        "page": page["page"],
                    })
                    if candidate:
                        candidates.append(candidate)

        elif source_type == "docx":
            for paragraph in document["paragraphs"]:
                source = {
                    "file_name": document["file_name"],
                    "paragraph": paragraph.get("paragraph"),
                    "style": paragraph.get("style"),
                }
                for key in ("table", "row", "column"):
                    if key in paragraph:
                        source[key] = paragraph[key]
                if paragraph.get("source_requirement_id"):
                    source["source_requirement_id"] = paragraph["source_requirement_id"]
                candidate = self._candidate(paragraph["text"], source)
                if candidate:
                    candidates.append(candidate)

        else:
            raise ValueError(
                f"Unsupported document source type: {source_type}"
            )

        return candidates

    @staticmethod
    def _split_text(text: str) -> List[str]:
        """Keep prose paragraphs intact and split only explicitly labeled lines."""
        blocks = [block for block in re.split(r"\n\s*\n+", text) if block.strip()]
        segments: List[str] = []
        explicit_id = re.compile(
            r"^\s*(?:[-*]\s*)?\(?[A-Za-z][A-Za-z0-9_-]*[-_]\d+(?:[.-]\d+)*\)?(?:\s|:|\.)"
        )
        for block in blocks:
            lines = [" ".join(line.split()) for line in block.splitlines() if line.strip()]
            if any(explicit_id.match(line) for line in lines):
                current: List[str] = []
                for line in lines:
                    if explicit_id.match(line) and current:
                        segments.append(" ".join(current))
                        current = []
                    current.append(line)
                if current:
                    segments.append(" ".join(current))
            else:
                segments.append(" ".join(lines))
        return segments

    @staticmethod
    def _contains_requirement_language(text: str) -> bool:
        return any(
            re.search(pattern, text.strip(), re.IGNORECASE)
            for pattern in RequirementDetector.REQUIREMENT_PATTERNS
        )

    def detect_text(self, text: str) -> List[Dict]:
        """Detect requirements in plain text using the same rules as files."""
        candidates = []
        for segment in self._split_text(text):
            candidate = self._candidate(segment, {})
            if candidate:
                candidates.append(candidate)
        return candidates
