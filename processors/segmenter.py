"""
Structure-aware segmentation of SRS documents into requirement candidates.

Earlier versions treated every paragraph, list item and table cell as an
independent candidate.  That lost structure:

- the bullets after "... shall reject the book when:" were dropped or became
  separate pseudo-requirements;
- a table of limits under a requirement was dropped cell by cell;
- glossary rows containing "must" became requirements.

This module first turns any input into an ordered list of *blocks*
(heading, paragraph, list item, table) and then groups blocks into
requirement candidates:

1. A block that starts with an explicit requirement ID (FR-002, NFR-01.1, ...)
   starts a new requirement.  A heading that carries an ID ("3.1 FR-01: User
   Authentication") starts a parent requirement; ID'd items under it are its
   children (parent_requirement_id).
2. Everything that follows a labelled requirement — paragraphs, list items,
   tables — belongs to it until the next ID or heading.
3. Without IDs, a sentence ending in ":" owns the list or table that follows;
   other paragraphs stand alone.
4. Requirement tables (an ID column) yield one requirement per row.
5. Non-requirement sections (purpose, scope, definitions, glossary, audience,
   references, product overview, assumptions, revision history, contents,
   traceability) and key/value tables (document metadata, glossaries) are
   skipped — and reported, so nothing disappears silently.  Content with an
   explicit requirement ID is never skipped.
6. An introduction ending in ":" with nothing after it is reported as a
   warning: the list or table it announces is missing from the input.  An
   unlabelled one-line introduction of that kind is not emitted.
7. Tables of contents, running PDF headers/footers and report-style sections
   that follow the specification (testing, results, conclusion) are skipped;
   "Section-2", "Figure-3", "Step-1" are never requirement IDs.
8. "Req-1/2" or "FR-3.1" is a child of "Req-1" / "FR-3" when that ID appears
   earlier in the document.  Exact repeats of an earlier requirement's text are
   dropped and reported as duplicates.
9. IDs may carry word segments ("FR-AUTH-01") or be compact with a known
   prefix and 3+ digits ("US001").  A repeated ID is merged into its first
   occurrence when it restates it in an acceptance/test section, otherwise
   renamed "<id>-2".  Traceability matrices are skipped (they map requirements
   to code).  Only reference-type sections (appendix, glossary, references,
   history, testing/results) skip their subsections; "2 System Overview" does
   not hide "2.4 User Stories".
10. Use-case template fields (Actors / Preconditions / Postconditions / Flow)
   under a heading form one requirement named after the use case.  Markdown
   fenced code blocks are skipped; words hyphenated across PDF line breaks are
   rejoined.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Requirement IDs
# ---------------------------------------------------------------------------

# Prefixes that are requirement IDs even without a label separator ("FR-1 The ...").
KNOWN_PREFIXES = {
    "FR", "NFR", "REQ", "R", "SR", "SRS", "UR", "BR", "FUNC", "NF", "F", "QR", "PR",
    "SEC", "PERF", "US", "UC", "SYS", "SWR", "HLR", "LLR", "RQ", "REQT", "FREQ", "NFREQ",
}
# FR-1, NFR-01.1, Req-1/2, FR-AUTH-01 (word segments before the number) ...
_ID_DASHED = r"[A-Za-z][A-Za-z0-9_]*(?:[-_][A-Za-z]+)*[-_]\d+(?:[./-]\d+)*"
# ... and compact IDs: a known prefix directly followed by 3+ digits (US001, FR012).
# Shorter compact labels ("REQ1") are not IDs: templates repeat them per feature.
_ID_COMPACT = r"(?:" + "|".join(sorted(KNOWN_PREFIXES, key=len, reverse=True)) + r")\d{3,}(?:[./-]\d+)*"
_ID = rf"(?:{_ID_DASHED}|{_ID_COMPACT})"
# Words that number parts of the *document*, not requirements ("Section-2 - It
# describes ...", "Figure-3", "Step-1").  Never read as requirement IDs.
NON_ID_PREFIXES = {
    "SECTION", "CHAPTER", "CH", "PART", "PAGE", "PG", "FIGURE", "FIG", "TABLE", "TAB",
    "APPENDIX", "ANNEX", "STEP", "VERSION", "VER", "V", "REV", "REVISION", "PHASE", "STAGE",
    "SPRINT", "RELEASE", "ITERATION", "LEVEL", "ROUND", "EXAMPLE", "EQ", "EQUATION", "LINE",
}
_LEADING_ID = re.compile(
    rf"^\s*(?:[-*•]\s*)?\(?(?P<id>{_ID})\)?(?P<after>\s*[:—–).]|\s+-\s|\s*$|\s+)"
)
_SECTION_NUMBER = re.compile(r"^\s*(?:\d+(?:\.\d+)*\.?|[A-Z]\.(?:\d+\.?)*)\s+(?=\S)")
_MARKDOWN_EMPHASIS = re.compile(r"^\s*(?:\*\*|__)(.*?)(?:\*\*|__)\s*", re.S)


def leading_requirement_id(text: str) -> Optional[str]:
    """
    The requirement ID a text starts with, or None.

    An ID needs a label separator after it (":", "—", "–", ")", ".", " - ") or
    a known prefix (FR, NFR, REQ, ...).  This keeps "SHA-256 hashing shall be
    used" or "UTF-8 encoding ..." from being read as requirement IDs.
    """
    text = _MARKDOWN_EMPHASIS.sub(lambda m: m.group(1) + " ", text, count=1)
    match = _LEADING_ID.match(text)
    if not match:
        return None
    rid = match.group("id")
    if re.fullmatch(_ID_COMPACT, rid, re.I) and not re.search(r"[-_]", rid):
        return rid if re.match(r"[A-Z]", rid) else None      # "US001" yes, "us001" no
    prefix = re.split(r"[-_]", rid, maxsplit=1)[0].upper()
    if prefix in NON_ID_PREFIXES:
        return None
    separator = match.group("after").strip()
    if separator or prefix in KNOWN_PREFIXES:
        return rid
    return None


def strip_section_number(text: str) -> str:
    return _SECTION_NUMBER.sub("", text.strip(), count=1)


def parent_of_id(rid: str) -> Optional[str]:
    """'Req-1/2' -> 'Req-1', 'FR-3.1' -> 'FR-3'; None when there is no sub-number."""
    match = re.match(r"^(?P<base>.+)[./]\d+$", rid)
    if match and re.fullmatch(_ID, match.group("base")):
        return match.group("base")
    return None


# ---------------------------------------------------------------------------
# Non-requirement sections
# ---------------------------------------------------------------------------

SKIP_SECTION_TERMS = (
    "purpose", "scope", "definition", "acronym", "abbreviation", "glossary", "terminology",
    "references", "overview", "audience", "document conventions", "conventions",
    "table of contents", "contents", "revision", "document history", "change history",
    "product perspective", "product functions", "user classes", "user characteristics",
    "assumption", "dependencies", "traceability", "appendix", "index",
    "risk", "future enhancement", "future work", "future scope", "out of scope",
    # Report-style sections that follow the specification (project reports often
    # append them to the SRS): they describe what was built or measured.
    "implementation and testing", "test plan", "test case", "test result", "testing methodolog",
    "conclusion", "lessons learned", "acknowledg", "bibliograph", "list of figures", "list of tables",
    "document organization", "document organisation", "structure of the document",
    "organization of the document", "organisation of the document",
)

# Words that are only safe to skip when they are the whole title: "Results" is a
# report section, "Search Results" may be a feature.
SKIP_SECTION_TITLES = re.compile(
    r"(?:testing|tests?|results?|results and discussion|discussion|evaluation|"
    r"evaluation and analysis|analysis and evaluation|experiments?|experimental results|"
    r"strengths(?: and (?:weaknesses|challenges|limitations))?|challenges|limitations|summary)"
)


# Sections whose *subsections* are skipped too: reference material and report
# chapters.  Other skipped sections ("2 System Overview", "Product Perspective")
# skip only their own text; each subsection ("2.4 User Stories") is judged on
# its own title.
SUBTREE_SKIP_TERMS = (
    "table of contents", "contents", "appendix", "references", "bibliograph", "glossary",
    "definition", "acronym", "abbreviation", "terminology", "revision", "document history",
    "change history", "acknowledg", "conclusion", "lessons learned", "list of figures",
    "list of tables", "index", "traceability", "future work", "future enhancement", "future scope",
    "implementation and testing", "test plan", "test case", "test result", "testing methodolog",
    # Project management and document metadata: plans, schedules, team, tooling.
    "project plan", "project schedule", "timeline", "milestone", "work allocation", "work breakdown",
    "contribution matrix", "planned contribution", "team members", "project team", "budget", "gantt",
    "tools and technologies", "technology stack", "tech stack", "document control", "metadata",
)
SKIP_SECTION_TERMS = SKIP_SECTION_TERMS + tuple(t for t in SUBTREE_SKIP_TERMS if t not in SKIP_SECTION_TERMS)
# Whole titles that are verification reports or acceptance checklists.  Their
# items that carry a requirement ID are never skipped (they are merged into the
# requirement, see _drop_duplicates); the rest is a report, not a requirement.
_REPORT_TITLES = re.compile(
    r"(?:acceptance criteria|verification(?: (?:and )?(?:validation|acceptance criteria))?|"
    r"validation summary|verification summary|tools|team|schedule)"
)


def is_skip_section(heading: str) -> bool:
    """
    True for sections that describe the document rather than the system.
    A heading that mentions requirements is never skipped, except a
    traceability matrix: it maps requirements to code, which is what the
    traceability pipeline must find on its own.  Skipped content is listed in
    the segmentation report, so it can be reviewed.
    """
    title = strip_section_number(heading).lower()
    if leading_requirement_id(strip_section_number(heading)):
        return False
    if re.search(r"\btraceability\b", title):
        return True
    if re.search(r"\brequirement", title):
        return False
    normalised = " ".join(re.sub(r"[^a-z ]+", " ", title).split())
    if SKIP_SECTION_TITLES.fullmatch(normalised) or _REPORT_TITLES.fullmatch(normalised):
        return True
    return any(re.search(rf"\b{re.escape(term)}", title) for term in SKIP_SECTION_TERMS)


def skips_subsections(heading: str) -> bool:
    """For a skipped section: are its subsections skipped as well?"""
    title = strip_section_number(heading).lower()
    if re.search(r"\btraceability\b", title):
        return True
    normalised = " ".join(re.sub(r"[^a-z ]+", " ", title).split())
    if SKIP_SECTION_TITLES.fullmatch(normalised) or _REPORT_TITLES.fullmatch(normalised):
        return True
    return any(re.search(rf"\b{re.escape(term)}", title) for term in SUBTREE_SKIP_TERMS)


# ---------------------------------------------------------------------------
# Tables of contents
# ---------------------------------------------------------------------------

_TOC_TITLE = re.compile(
    r"^\s*(?:table of contents|contents|list of (?:figures|tables)|index of (?:figures|tables))\s*:?\s*$",
    re.I,
)
_TOC_LEADER = re.compile(r"(?:\.\s?){4,}|…{2,}|_{4,}")
_TRAILING_PAGE = re.compile(r"(?:\S\s+|[.…_·]\s*)(?:\d{1,3}|[ivxlc]{1,6})\s*$", re.I)
_MODAL = re.compile(r"\b(?:shall|must|should|will|may|can)\b", re.I)


def is_toc_line(line: str, in_toc: bool = False) -> bool:
    """
    A table-of-contents entry: a title followed by a page number.  Anywhere in
    the document a dot leader ("Purpose ........ 4") marks one; inside a
    contents list a plain trailing page number does ("Overview  6").
    """
    text = line.strip()
    if not text or not _TRAILING_PAGE.search(text) or _MODAL.search(text):
        return False
    if _TOC_LEADER.search(text):
        return True
    return in_toc and len(text.split()) <= 14


# ---------------------------------------------------------------------------
# Blocks
# ---------------------------------------------------------------------------


@dataclass
class Block:
    kind: str                                  # heading | paragraph | list_item | table
    text: str = ""
    level: int = 1                             # heading level
    rows: List[List[str]] = field(default_factory=list)   # table rows (first may be a header)
    location: Dict[str, Any] = field(default_factory=dict)


def _heading_level(style: str, text: str) -> int:
    match = re.search(r"heading\s*(\d)", style, re.I)
    if match:
        return int(match.group(1))
    number = re.match(r"^\s*(\d+(?:\.\d+)*)", text)
    return number.group(1).count(".") + 1 if number else 1


def blocks_from_docx(document) -> List[Block]:
    """Blocks from a python-docx Document, in body order."""
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    blocks: List[Block] = []
    paragraph_index = table_index = 0
    for child in document.element.body.iterchildren():
        if child.tag == qn("w:p"):
            paragraph_index += 1
            paragraph = Paragraph(child, document)
            text = paragraph.text.strip()
            if not text:
                continue
            style = paragraph.style.name if paragraph.style is not None else ""
            ppr = child.find(qn("w:pPr"))
            numbered = ppr is not None and ppr.find(qn("w:numPr")) is not None
            location = {"paragraph": paragraph_index, "style": style}
            if re.match(r"toc\b", style, re.I) or is_toc_line(text):
                blocks.append(Block("toc", text, location=location))
            elif re.match(r"(heading|title)", style, re.I):
                blocks.append(Block("heading", text, _heading_level(style, text), location=location))
            elif numbered or style.lower().startswith("list"):
                blocks.append(Block("list_item", text, location=location))
            else:
                blocks.append(Block("paragraph", text, location=location))
        elif child.tag == qn("w:tbl"):
            table_index += 1
            table = Table(child, document)
            rows = []
            for row in table.rows:
                cells = []
                for cell in row.cells:
                    cells.append(" ".join(p.text.strip() for p in cell.paragraphs if p.text.strip()))
                if any(cells):
                    rows.append(cells)
            if rows:
                blocks.append(Block("table", rows=rows, location={"table": table_index}))
    return blocks


def block_to_dict(block: Block) -> Dict[str, Any]:
    return {"kind": block.kind, "text": block.text, "level": block.level,
            "rows": block.rows, "location": block.location}


def blocks_from_docx_dicts(items: List[Dict[str, Any]]) -> List[Block]:
    """Rebuild blocks from DOCXParser output (which keeps them JSON-friendly)."""
    return [Block(i["kind"], i.get("text", ""), i.get("level", 1), i.get("rows") or [],
                  dict(i.get("location") or {})) for i in items]


_BULLET = re.compile(r"^\s*(?:[•●▪◦‣∙*]|[-–](?=\s)|\d+[.)](?=\s)|[a-z][.)](?=\s)|\([a-z0-9]+\))\s*")
_MD_HEADING = re.compile(r"^\s*(#{1,6})\s+(.*)$")
_MD_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
_MD_TABLE_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(?:\|\s*:?-{2,}:?\s*)*\|?\s*$")
_NUMBERED_HEADING = re.compile(r"^\s*\d+(?:\.\d+)*\.?\s+[A-Z][^\n]{0,90}$")


def _looks_like_heading(line: str) -> bool:
    """A numbered, short line without sentence punctuation, e.g. '3.4 Fines'."""
    stripped = line.strip()
    if not _NUMBERED_HEADING.match(stripped) or stripped.endswith((".", ";", ",", ":")):
        return False
    title = strip_section_number(stripped)
    if "%" in title or re.search(r"\d\)?$", title):
        return False          # table cells such as "1 Critical (5%)" or "1 Sprint 1", not headings
    words = title.split()
    return 1 <= len(words) <= 12 and not re.search(r"\b(shall|must|should|will)\b", stripped, re.I)


def blocks_from_lines(lines: List[Tuple[str, Dict[str, Any]]]) -> List[Block]:
    """
    Blocks from text lines (PDF pages, plain text, Markdown).

    Wrapped lines are joined into one paragraph; a blank line, a bullet, a
    heading, a table row or a line starting with a requirement ID ends it.
    """
    blocks: List[Block] = []
    current: Optional[Block] = None
    table: Optional[Block] = None
    in_toc = False                 # inside a "Table of Contents" list
    toc_misses = 0                 # consecutive non-entry lines seen while in_toc
    code: Optional[Block] = None   # inside a Markdown ``` fenced block (code, ASCII diagrams)

    def flush():
        nonlocal current, table
        if current is not None:
            current.text = " ".join(current.text.split())
            blocks.append(current)
            current = None
        if table is not None:
            blocks.append(table)
            table = None

    for raw, location in lines:
        # Fenced code blocks hold code, commands or ASCII diagrams, not requirements.
        if re.match(r"\s*(?:```|~~~)", raw):
            if code is None:
                flush()
                code = Block("code", "", location=dict(location))
            else:
                blocks.append(code)
                code = None
            continue
        if code is not None:
            code.text += raw.rstrip() + "\n"
            continue
        line = raw.rstrip().replace("**", "").replace("__", "")    # Markdown emphasis
        if not line.strip() or re.fullmatch(r"\s*(?:-{3,}|\*{3,}|_{3,})\s*", line):
            flush()
            continue
        # Tables of contents: the title becomes a (skipped) heading, entries
        # become 'toc' blocks.  Entries must never become headings, or they
        # would end the skipped contents section early.
        if _TOC_TITLE.match(line.lstrip("#").strip()):
            flush()
            blocks.append(Block("heading", line.lstrip("#").strip(), 1, location=dict(location)))
            in_toc, toc_misses = True, 0
            continue
        if is_toc_line(line, in_toc):
            flush()
            blocks.append(Block("toc", line.strip(), location=dict(location)))
            toc_misses = 0
            continue
        if in_toc:
            toc_misses += 1
            if toc_misses >= 3:
                in_toc = False
        md_heading = _MD_HEADING.match(line)
        if md_heading:
            flush()
            text = md_heading.group(2).strip().strip("*_ ")
            blocks.append(Block("heading", text, len(md_heading.group(1)), location=dict(location)))
            continue
        if _MD_TABLE_ROW.match(line):
            if current is not None:
                current.text = " ".join(current.text.split())
                blocks.append(current)
                current = None
            if _MD_TABLE_SEPARATOR.match(line):
                continue
            cells = [c.strip().strip("*_ ") for c in line.strip().strip("|").split("|")]
            if table is None:
                table = Block("table", rows=[], location=dict(location))
            table.rows.append(cells)
            continue
        if table is not None:
            blocks.append(table)
            table = None
        if _looks_like_heading(line) and not leading_requirement_id(line):
            flush()
            blocks.append(Block("heading", line.strip(), _heading_level("", line), location=dict(location)))
            continue
        bullet = _BULLET.match(line)
        starts_id = leading_requirement_id(line) is not None
        if not bullet and not starts_id and _UC_STRONG_FIELD.match(line):
            flush()                    # "Actors:", "Preconditions:" ... never continue a paragraph
            current = Block("paragraph", line.strip(), location=dict(location))
            continue
        if bullet and not starts_id:
            flush()
            current = Block("list_item", line[bullet.end():], location=dict(location))
            continue
        if starts_id:
            flush()
            current = Block("paragraph", line, location=dict(location))
            continue
        if (current is not None and current.kind == "list_item"
                and current.text.rstrip().endswith((".", "!", "?")) and line.lstrip()[:1].isupper()):
            # A finished bullet followed by a capitalised line: a new paragraph,
            # not a wrapped continuation of the bullet.
            flush()
        if current is None:
            current = Block("paragraph", line, location=dict(location))
        elif (re.search(r"[A-Za-z]-$", current.text.rstrip()) and re.match(r"[a-z]", line.strip())
              and not re.match(r"(?:and|or|nor|to)\b", line.strip())):
            # A word hyphenated across a line break: "cre-" + "dentials".
            current.text = current.text.rstrip()[:-1] + line.strip()
        else:
            current.text += " " + line.strip()
    if code is not None:                       # unterminated fence: keep it as code
        blocks.append(code)
    flush()
    return blocks


# Five or more single letters separated by single spaces: "p r e s c r i b e d".
_LETTER_SPACED = re.compile(r"(?<![A-Za-z])(?:[A-Za-z] ){4,}[A-Za-z](?![A-Za-z])")


def _running_line_key(line: str) -> str:
    return re.sub(r"\d+", "#", " ".join(line.lower().split()))


def running_headers_footers(pages: List[Dict[str, Any]], edge: int = 2) -> set:
    """
    Normalised lines that repeat at the top or bottom of most pages (running
    headers, footers, 'Page N' lines).  Digits are ignored, so 'Page 2' and
    'Page 3' are the same line.
    """
    if len(pages) < 3:
        return set()
    counts: Dict[str, int] = {}
    for page in pages:
        lines = [l for l in page["text"].splitlines() if l.strip()]
        for key in {_running_line_key(l) for l in lines[:edge] + lines[-edge:]}:
            counts[key] = counts.get(key, 0) + 1
    threshold = max(3, (len(pages) + 1) // 2)
    # Requirement text is never a header, even if it repeats with other numbers.
    return {k for k, n in counts.items()
            if n >= threshold and len(k) >= 3 and not _MODAL.search(k)
            and not leading_requirement_id(k.replace("#", "1"))}


def blocks_from_pdf(document: Dict[str, Any]) -> List[Block]:
    """Blocks from PDF pages, without running headers and footers."""
    repeated = running_headers_footers(document["pages"])
    lines = []
    for page in document["pages"]:
        page_lines = page["text"].splitlines()
        nonblank = [i for i, l in enumerate(page_lines) if l.strip()]
        edges = set(nonblank[:2] + nonblank[-2:])
        for i, line in enumerate(page_lines):
            if i in edges and _running_line_key(line) in repeated:
                continue
            line = _LETTER_SPACED.sub(lambda m: m.group(0).replace(" ", ""), line)
            lines.append((line, {"page": page["page"]}))
    return blocks_from_lines(lines)


def blocks_from_text(text: str) -> List[Block]:
    return blocks_from_lines([(line, {}) for line in text.splitlines()])


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------


def _id_column(rows: List[List[str]]) -> Optional[int]:
    """Index of a column holding requirement IDs in most body rows."""
    body = rows[1:] if len(rows) > 1 else rows
    if not body:
        return None
    width = max(len(r) for r in rows)
    for col in range(width):
        hits = sum(1 for r in body if col < len(r) and leading_requirement_id(r[col] + ":")
                   and re.fullmatch(rf"\(?{_ID}\)?[:.]?", r[col].strip()))
        if hits >= max(1, (len(body) + 1) // 2):
            return col
    return None


def _has_header(rows: List[List[str]]) -> bool:
    if len(rows) < 2:
        return False
    header = rows[0]
    return all(cell and len(cell.split()) <= 4 and not re.search(r"\d", cell) for cell in header)


def _is_key_value_table(rows: List[List[str]]) -> bool:
    """Two-column label/value tables: document metadata, glossaries."""
    if any(len(r) != 2 for r in rows):
        return False
    labels = [r[0] for r in rows]
    return all(len(label.split()) <= 5 and not re.search(r"\b(shall|must|should)\b", label, re.I)
               for label in labels)


def table_as_items(rows: List[List[str]]) -> List[str]:
    """Render table rows as 'Header: value; Header: value' items."""
    if _has_header(rows):
        header, body = rows[0], rows[1:]
        return ["; ".join(f"{h}: {v}" if h else v for h, v in zip(header, r) if v) for r in body]
    return [" | ".join(c for c in r if c) for r in rows]


# ---------------------------------------------------------------------------
# Grouping
# ---------------------------------------------------------------------------


@dataclass
class Segment:
    requirement_id: Optional[str]
    parent_id: Optional[str] = None
    lines: List[Tuple[str, str]] = field(default_factory=list)   # (kind, text)
    location: Dict[str, Any] = field(default_factory=dict)
    section: str = ""
    expects_items: bool = False
    has_items: bool = False

    @property
    def text(self) -> str:
        out: List[str] = []
        for kind, text in self.lines:
            out.append(f"- {text}" if kind == "item" else text)
        return "\n".join(out)

    def add(self, kind: str, text: str, location: Dict[str, Any]) -> None:
        if not self.lines:
            self.location = dict(location)
        else:
            for key in ("paragraph", "page"):
                if key in location:
                    self.location[f"{key}_end"] = location[key]
        self.lines.append((kind, text))
        if kind == "item":
            self.has_items = True
            self.expects_items = False
        else:
            self.expects_items = text.rstrip().endswith(":")


@dataclass
class SegmentationReport:
    skipped_sections: List[Dict[str, Any]] = field(default_factory=list)
    skipped_tables: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[Dict[str, Any]] = field(default_factory=list)
    toc_lines: List[str] = field(default_factory=list)
    duplicates: List[Dict[str, Any]] = field(default_factory=list)
    repeated_ids: List[Dict[str, Any]] = field(default_factory=list)
    code_blocks: List[Dict[str, Any]] = field(default_factory=list)


def _dedupe_key(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())


# A source-code file path ("accounts/models.py", "src/App.java").
_CODE_PATH = re.compile(r"\b[\w./-]+\.(?:py|java|js|jsx|ts|tsx|cs|cpp|cc|c|h|hpp|go|rb|php|kt|swift|scala|rs)\b")

# Sections that restate earlier requirements to say how they are checked.
_CRITERIA_SECTION = re.compile(r"\b(?:acceptance|criteria|verification|validation|tests?|testing)\b", re.I)


def _drop_duplicates(segments: List[Segment], report: SegmentationReport) -> List[Segment]:
    """
    Drop a segment whose text repeats an earlier one (same words, ignoring case
    and punctuation).  Two different source IDs with the same text are both
    kept: the document numbers them as separate requirements.

    A source ID that appears again with different text is not emitted twice:
    - in an acceptance / verification / test section it restates how the
      requirement is checked, so its text is merged into the first occurrence;
    - anywhere else the document reuses the label (e.g. "REQ-1" under every
      feature), so the later one is renamed "<id>-<n>" to stay unique.
    Both cases are listed in report.repeated_ids.
    """
    seen: Dict[str, Segment] = {}
    by_id: Dict[str, Segment] = {}
    taken = {s.requirement_id.casefold() for s in segments if s.requirement_id}
    kept: List[Segment] = []
    for seg in segments:
        key = _dedupe_key(seg.text)
        first = seen.get(key)
        if key and first is not None and (seg.requirement_id is None or seg.requirement_id == first.requirement_id):
            report.duplicates.append({"requirement_id": seg.requirement_id, "duplicate_of": first.requirement_id,
                                      "text": seg.text, "location": seg.location,
                                      "first_location": first.location})
            continue
        rid = seg.requirement_id
        if rid and rid.casefold() in by_id:
            original = by_id[rid.casefold()]
            if _CODE_PATH.search(seg.text):
                # "FR-1 Secure Auth accounts/models.py accounts/tests.py": a
                # traceability row that maps the requirement to code files.
                # It is not a requirement, and it would give the answer away.
                report.repeated_ids.append({"requirement_id": rid, "action": "dropped: maps the requirement to code files",
                                            "section": seg.section, "location": seg.location})
                continue
            if _CRITERIA_SECTION.search(seg.section or ""):
                original.lines.append(("text", f"[{strip_section_number(seg.section)}] {seg.text}"))
                report.repeated_ids.append({"requirement_id": rid, "action": "merged into first occurrence",
                                            "section": seg.section, "location": seg.location})
                continue
            n = 2
            while f"{rid}-{n}".casefold() in taken:
                n += 1
            seg.requirement_id = f"{rid}-{n}"
            taken.add(seg.requirement_id.casefold())
            report.repeated_ids.append({"requirement_id": rid, "action": f"renamed to {seg.requirement_id}",
                                        "section": seg.section, "location": seg.location})
        if seg.requirement_id:
            by_id.setdefault(seg.requirement_id.casefold(), seg)
        seen.setdefault(key, seg)
        kept.append(seg)
    return kept


# Use-case template fields.  A strong field starts grouping a section into one
# use case; once grouping, every field and bullet of the section joins it.
_UC_STRONG_FIELD = re.compile(
    r"^\s*(?:primary\s+|secondary\s+)?(?:actors?|pre-?\s?conditions?|post-?\s?conditions?|"
    r"(?:main|basic|normal)\s+(?:flow|course|scenario)s?(?:\s+of\s+events)?|flow\s+of\s+events|flows?)\s*:",
    re.I,
)


def segment(blocks: List[Block]) -> Tuple[List[Segment], SegmentationReport]:
    report = SegmentationReport()
    segments: List[Segment] = []
    current: Optional[Segment] = None
    section_title = ""
    section_id: Optional[str] = None           # ID carried by the current heading, if any
    skip_level: Optional[int] = None
    skip_subtree = False                       # does the skipped section also skip its subsections?
    use_case = False                           # current section is being grouped as one use case
    seen_ids: set = set()

    def close():
        nonlocal current, use_case
        use_case = False
        if current is not None and current.lines:
            if current.expects_items and not current.has_items:
                # An unlabelled one-line introduction ("The following documents
                # shall be prepared:") without its list carries no requirement
                # content of its own: report it instead of emitting it.
                dropped = current.requirement_id is None and len(current.lines) == 1
                report.warnings.append({
                    "type": "missing_list",
                    "requirement_id": current.requirement_id,
                    "text": current.lines[-1][1],
                    "message": "Text introduces a list or table that is not present in the input."
                               + (" The introduction was not extracted." if dropped else ""),
                    "dropped": dropped,
                    "location": current.location,
                })
                if dropped:
                    current = None
                    return
            if current.requirement_id:
                seen_ids.add(current.requirement_id)
            segments.append(current)
        current = None

    for block in blocks:
        if block.kind == "toc":
            close()
            report.toc_lines.append(block.text)
            continue
        if block.kind == "code":
            close()
            report.code_blocks.append({"first_line": block.text.strip().split("\n")[0][:120],
                                       "lines": block.text.count("\n"), "location": block.location})
            continue
        if block.kind == "heading":
            close()
            title = strip_section_number(block.text)
            rid = leading_requirement_id(title)
            if skip_level is not None and (block.level <= skip_level or not skip_subtree):
                skip_level = None
            if rid is None and skip_level is None and is_skip_section(block.text):
                skip_level = block.level
                skip_subtree = skips_subsections(block.text)
                report.skipped_sections.append({"heading": block.text, "location": block.location})
            section_title = block.text
            section_id = rid
            if rid:
                # A heading such as "3.1 FR-01: User Authentication" is itself a requirement.
                current = Segment(rid, section=section_title)
                current.add("text", title, block.location)
            continue

        texts = [block.text] if block.kind != "table" else []
        rid = leading_requirement_id(block.text) if block.kind != "table" else None

        if skip_level is not None and rid is None:
            if block.kind == "table":
                continue
            report.skipped_sections[-1].setdefault("items", []).append(block.text)
            continue

        if block.kind == "table":
            rows = block.rows
            id_col = _id_column(rows)
            if id_col is not None:                   # requirement table: one requirement per row
                close()
                header = rows[0] if _has_header(rows) else None
                for r_index, row in enumerate(rows[1:] if header else rows, start=2 if header else 1):
                    row_id = re.sub(r"[():.]", "", row[id_col]).strip() if id_col < len(row) else ""
                    if not leading_requirement_id(row_id + ":"):
                        continue
                    others = [(header[i] if header and i < len(header) else "", c)
                              for i, c in enumerate(row) if i != id_col and c]
                    main = max(others, key=lambda hc: len(hc[1]))[1] if others else ""
                    extra = "; ".join(f"{h}: {c}" for h, c in others if c != main and h)
                    parent = section_id
                    if parent is None and parent_of_id(row_id) in seen_ids:
                        parent = parent_of_id(row_id)
                    seg = Segment(row_id, parent_id=parent, section=section_title)
                    seg.add("text", f"{row_id}: {main}" + (f" ({extra})" if extra else ""),
                            {**block.location, "row": r_index})
                    segments.append(seg)
                    seen_ids.add(row_id)
                continue
            if current is not None and (current.requirement_id or current.expects_items):
                for item in table_as_items(rows):
                    current.add("item", item, block.location)
                continue
            if _is_key_value_table(rows):
                close()
                report.skipped_tables.append({"reason": "key/value table (metadata or glossary)",
                                              "first_row": rows[0], "location": block.location})
                continue
            close()                                  # standalone table: each row stands alone
            for r_index, item in enumerate(table_as_items(rows), start=1):
                seg = Segment(None, section=section_title)
                seg.add("text", item, {**block.location, "row": r_index})
                segments.append(seg)
            continue

        text = texts[0]
        if use_case and rid is None:                # rest of a use case's fields and bullets
            current.add("item" if block.kind == "list_item" else "text", text, block.location)
            continue
        if (rid is None and section_title and _UC_STRONG_FIELD.match(text)
                and not (current is not None and current.requirement_id)):
            # "Actors:", "Preconditions:", "Main flow:" ... under a use-case
            # heading: the heading and all its fields form one requirement.
            close()
            name = strip_section_number(section_title)
            last = segments[-1] if segments else None
            if (last is not None and last.requirement_id is None and last.section == section_title
                    and len(last.lines) == 1 and len(last.text.split()) <= 6
                    and not re.search(r"[.!?:;]$", last.text.strip())):
                # The use-case title wrapped onto the line before its first
                # field ("4.1.3 View" + "medical history"): take it back.
                name = f"{name} {segments.pop().text.strip()}"
            current = Segment(None, section=section_title)
            current.add("text", f"Use case: {name}", block.location)
            current.add("text", text, block.location)
            use_case = True
            continue
        if rid is not None:
            close()
            parent = section_id if section_id and section_id != rid else None
            if parent is None and parent_of_id(rid) in seen_ids:
                parent = parent_of_id(rid)          # "Req-1/2" under an earlier "Req-1"
            current = Segment(rid, parent_id=parent, section=section_title)
            current.add("text", text, block.location)
            continue

        if current is not None and (current.requirement_id or
                                    (block.kind == "list_item" and (current.expects_items or current.has_items))):
            current.add("item" if block.kind == "list_item" else "text", text, block.location)
            continue

        close()
        current = Segment(None, section=section_title)
        current.add("text", text, block.location)
        if not text.rstrip().endswith(":"):
            close()      # an unlabelled paragraph or bullet without an introduction stands alone
    close()
    return _drop_duplicates(segments, report), report
