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
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Requirement IDs
# ---------------------------------------------------------------------------

_ID = r"[A-Za-z][A-Za-z0-9_]*[-_]\d+(?:[./-]\d+)*"      # FR-1, NFR-01.1, Req-1/2
# Prefixes that are requirement IDs even without a label separator ("FR-1 The ...").
KNOWN_PREFIXES = {
    "FR", "NFR", "REQ", "R", "SR", "SRS", "UR", "BR", "FUNC", "NF", "F", "QR", "PR",
    "SEC", "PERF", "US", "UC", "SYS", "SWR", "HLR", "LLR", "RQ", "REQT", "FREQ", "NFREQ",
}
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
    match = re.match(rf"^(?P<base>[A-Za-z][A-Za-z0-9_]*[-_]\d+(?:[./-]\d+)*)[./]\d+$", rid)
    return match.group("base") if match else None


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


def is_skip_section(heading: str) -> bool:
    """
    True for sections that describe the document rather than the system.
    A heading that mentions requirements is never skipped.  Skipped content
    is listed in the segmentation report, so it can be reviewed.
    """
    title = strip_section_number(heading).lower()
    if leading_requirement_id(strip_section_number(heading)):
        return False
    if re.search(r"\brequirement", title):
        return False
    if SKIP_SECTION_TITLES.fullmatch(re.sub(r"[^a-z ]+", " ", title).strip()):
        return True
    return any(re.search(rf"\b{re.escape(term)}", title) for term in SKIP_SECTION_TERMS)


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
    words = strip_section_number(stripped).split()
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
        else:
            current.text += " " + line.strip()
    flush()
    return blocks


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


def _dedupe_key(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())


def _drop_duplicates(segments: List[Segment], report: SegmentationReport) -> List[Segment]:
    """
    Drop a segment whose text repeats an earlier one (same words, ignoring case
    and punctuation).  Two different source IDs with the same text are both
    kept: the document numbers them as separate requirements.
    """
    seen: Dict[str, Segment] = {}
    kept: List[Segment] = []
    for seg in segments:
        key = _dedupe_key(seg.text)
        first = seen.get(key)
        if key and first is not None and (seg.requirement_id is None or seg.requirement_id == first.requirement_id):
            report.duplicates.append({"requirement_id": seg.requirement_id, "duplicate_of": first.requirement_id,
                                      "text": seg.text, "location": seg.location,
                                      "first_location": first.location})
            continue
        seen.setdefault(key, seg)
        kept.append(seg)
    return kept


def segment(blocks: List[Block]) -> Tuple[List[Segment], SegmentationReport]:
    report = SegmentationReport()
    segments: List[Segment] = []
    current: Optional[Segment] = None
    section_title = ""
    section_id: Optional[str] = None           # ID carried by the current heading, if any
    skip_level: Optional[int] = None
    seen_ids: set = set()

    def close():
        nonlocal current
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
        if block.kind == "heading":
            close()
            title = strip_section_number(block.text)
            rid = leading_requirement_id(title)
            if skip_level is not None and block.level <= skip_level:
                skip_level = None
            if rid is None and skip_level is None and is_skip_section(block.text):
                skip_level = block.level
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
