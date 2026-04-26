from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


SourceType = Literal[
    "CMS_NCD",
    "CMS_LCD",
    "CMS_MANUAL",
    "INSURER_POLICY",
    "SPECIALTY_GUIDELINE",
    "APPEALS_PRECEDENT",
    "OTHER",
]
QueryStrategy = Literal["exact_code", "semantic", "hybrid", "policy_lookup", "manual"]
CoveragePosition = Literal["supports_appeal", "supports_denial", "neutral", "unclear"]


class ExternalEvidenceTask(BaseModel):
    case_id: str
    schema_version: str = "1.0"
    status: str = "pending"
    provenance: dict[str, Any] = Field(default_factory=dict)
    search_queries: list[str] = Field(default_factory=list)
    preferred_sources: list[str] = Field(default_factory=list)
    denial_category: str | None = None
    insurer: str | None = None
    denied_procedures: list[str] = Field(default_factory=list)
    diagnosis: list[str] = Field(default_factory=list)
    codes: dict[str, list[str]] = Field(default_factory=dict)


class EvidenceQuery(BaseModel):
    query: str
    strategy: QueryStrategy
    top_k: int = 8
    codes: list[str] = Field(default_factory=list)
    source_types: list[SourceType] = Field(default_factory=list)
    insurer: str | None = None
    rationale: str | None = None


class QueryTrace(BaseModel):
    query: str
    strategy: QueryStrategy
    top_k: int
    result_count: int
    rationale: str | None = None


class CitationSource(BaseModel):
    title: str
    url: str
    citation_label: str
    source_type: SourceType
    effective_date: str | None = None


class ExternalCitation(BaseModel):
    citation_id: str
    source_type: SourceType
    title: str
    url: str | None = None
    document_id: str | None = None
    section: str | None = None
    quote: str
    quote_start_char: int | None = None
    quote_end_char: int | None = None
    matched_codes: list[str] = Field(default_factory=list)
    matched_terms: list[str] = Field(default_factory=list)
    coverage_position: CoveragePosition = "supports_appeal"
    relevance_score: float = Field(ge=0, le=1)
    authority_score: float = Field(ge=0, le=1)
    usable_in_draft: bool = True
    citation: CitationSource


class ExternalEvidenceData(BaseModel):
    source_task_ref: str
    query_traces: list[QueryTrace]
    citations: list[ExternalCitation]
    rejected_sources: list[dict[str, Any]] = Field(default_factory=list)
    source_coverage_summary: str
    evidence_gaps: list[dict[str, Any]] = Field(default_factory=list)
    notes_for_strategy_agent: list[str] = Field(default_factory=list)


class ExternalEvidenceArtifact(BaseModel):
    case_id: str
    schema_version: str = "1.0"
    status: Literal["success", "partial", "failed"] = "success"
    provenance: dict[str, Any] = Field(default_factory=dict)
    data: ExternalEvidenceData
