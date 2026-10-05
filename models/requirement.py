from pydantic import BaseModel, Field
from typing import List, Literal, Optional


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
    id_source: Literal["source", "generated"] = "generated"

    # Original text is preserved exactly for traceability.
    raw_text: str

    # LLM-derived interpretation used for semantic processing and retrieval.
    normalized_text: str

    type: Literal["functional", "non-functional", "other"]
    subtype: str = "general"
    title: str

    # Keep every extraction array present in the model response. Empty arrays
    # are valid, but must be an explicit extraction decision.
    actor: List[str] = Field(...)
    actions: List[str] = Field(...)
    entities: List[str] = Field(...)

    inputs: List[str] = Field(...)
    outputs: List[str] = Field(...)

    preconditions: List[str] = Field(...)
    postconditions: List[str] = Field(...)
    conditions: List[str] = Field(...)

    constraints: List[str] = Field(...)
    error_conditions: List[str] = Field(...)

    # Terms and alternative wording improve lexical and semantic retrieval.
    domain_terms: List[str] = Field(...)
    synonyms: List[str] = Field(...)

    # Complex requirements can be decomposed into smaller implementation concepts.
    sub_requirements: List[str] = Field(...)

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
