from pydantic import BaseModel, Field
from typing import List, Optional


class SourceLocation(BaseModel):
    """Tracks where a requirement originated in the source SRS."""

    document_id: Optional[str] = None
    file_name: Optional[str] = None
    section: Optional[str] = None
    subsection: Optional[str] = None
    page: Optional[int] = None
    paragraph: Optional[int] = None
    table: Optional[int] = None
    row: Optional[int] = None
    column: Optional[int] = None


class Requirement(BaseModel):
    """Canonical representation of a single requirement used by downstream agents."""

    requirement_id: str = ""

    # Original text is preserved exactly for traceability.
    raw_text: str

    # LLM-derived interpretation used for semantic processing and retrieval.
    normalized_text: str

    type: str
    title: str

    actor: List[str] = Field(default_factory=list)
    actions: List[str] = Field(default_factory=list)
    entities: List[str] = Field(default_factory=list)

    inputs: List[str] = Field(default_factory=list)
    outputs: List[str] = Field(default_factory=list)

    preconditions: List[str] = Field(default_factory=list)
    postconditions: List[str] = Field(default_factory=list)
    conditions: List[str] = Field(default_factory=list)

    constraints: List[str] = Field(default_factory=list)
    error_conditions: List[str] = Field(default_factory=list)

    # Terms and alternative wording improve lexical and semantic retrieval.
    domain_terms: List[str] = Field(default_factory=list)
    synonyms: List[str] = Field(default_factory=list)

    # Complex requirements can be decomposed into smaller implementation concepts.
    sub_requirements: List[str] = Field(default_factory=list)

    # Search-oriented representation consumed by the Retrieval Agent.
    retrieval_text: str

    source: SourceLocation = Field(default_factory=SourceLocation)


class SRSMetadata(BaseModel):
    """Metadata describing the source from which requirements were extracted."""

    document_id: Optional[str] = None
    file_name: Optional[str] = None
    source_type: str
    total_requirements: int = 0


class SRSOutput(BaseModel):
    """Standard output of the SRS Agent regardless of input format."""

    analysis_id: str
    source: SRSMetadata
    requirements: List[Requirement] = Field(default_factory=list)
