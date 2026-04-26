from __future__ import annotations

import math
import os
import re
from collections import Counter
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

import certifi
from dotenv import load_dotenv
from pymongo import MongoClient

from query_planner import build_queries, extract_codes
from schemas import (
    CitationSource,
    EvidenceQuery,
    ExternalCitation,
    ExternalEvidenceArtifact,
    ExternalEvidenceData,
    ExternalEvidenceTask,
    QueryTrace,
)


AGENT_DIR = Path(__file__).resolve().parent
AUTHORITY_SCORE = {
    "CMS_NCD": 1.0,
    "CMS_LCD": 0.9,
    "CMS_MANUAL": 0.85,
    "INSURER_POLICY": 0.75,
    "SPECIALTY_GUIDELINE": 0.65,
    "APPEALS_PRECEDENT": 0.55,
    "OTHER": 0.35,
}
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "for",
    "from",
    "in",
    "is",
    "of",
    "or",
    "the",
    "to",
    "with",
}


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def tokenize(text: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[A-Za-z0-9]+", text.lower())
        if len(token) > 2 and token not in STOPWORDS
    ]


class MongoEvidenceStore:
    def __init__(self) -> None:
        load_dotenv(AGENT_DIR / ".env")
        uri = os.getenv("MONGODB_URI")
        if not uri or "<" in uri:
            raise ValueError("MONGODB_URI is missing or still contains placeholders.")
        client = MongoClient(uri, serverSelectionTimeoutMS=12000, tlsCAFile=certifi.where())
        client.admin.command("ping")
        db = client[os.getenv("MONGODB_DB", "counterclaim")]
        self.chunks = db[os.getenv("MONGODB_EVIDENCE_CHUNKS_COLLECTION", "evidence_chunks")]

    def search(self, query: EvidenceQuery) -> list[dict[str, Any]]:
        mongo_filter: dict[str, Any] = {}
        if query.codes:
            mongo_filter["codes"] = {"$in": query.codes}
        if query.source_types:
            mongo_filter["source_type"] = {"$in": query.source_types}

        candidates = list(self.chunks.find(mongo_filter, {"_id": 0}))
        if not candidates and query.source_types:
            candidates = list(self.chunks.find({"source_type": {"$in": query.source_types}}, {"_id": 0}))
        if not candidates:
            candidates = list(self.chunks.find({}, {"_id": 0}).limit(250))

        scored = [score_candidate(candidate, query) for candidate in candidates]
        scored = [candidate for candidate in scored if candidate["_score"] > 0]
        scored.sort(key=lambda candidate: candidate["_score"], reverse=True)
        return scored[: query.top_k]


def score_candidate(candidate: dict[str, Any], query: EvidenceQuery) -> dict[str, Any]:
    query_terms = set(tokenize(query.query))
    text_terms = Counter(tokenize(candidate.get("text", "")))
    metadata_terms = set(candidate.get("condition_terms", []) + candidate.get("service_terms", []))
    metadata_tokens = set(tokenize(" ".join(metadata_terms)))

    term_hits = [term for term in query_terms if text_terms[term] or term in metadata_tokens]
    keyword_score = len(term_hits) / max(len(query_terms), 1)

    candidate_codes = set(candidate.get("codes", []))
    exact_code = 1.0 if query.codes and candidate_codes.intersection(query.codes) else 0.0

    insurer_score = 0.0
    if query.insurer and candidate.get("insurer"):
        insurer_score = 1.0 if query.insurer.lower() == candidate["insurer"].lower() else 0.0

    authority_score = AUTHORITY_SCORE.get(candidate.get("source_type", "OTHER"), 0.35)
    citation_score = 1.0 if candidate.get("citation", {}).get("url") else 0.0

    final_score = (
        0.40 * keyword_score
        + 0.25 * exact_code
        + 0.20 * authority_score
        + 0.10 * insurer_score
        + 0.05 * citation_score
    )
    candidate = dict(candidate)
    candidate["_score"] = round(min(final_score, 1.0), 4)
    candidate["_matched_terms"] = sorted(term_hits)
    candidate["_authority_score"] = authority_score
    candidate["_exact_code_score"] = exact_code
    return candidate


def candidate_to_citation(candidate: dict[str, Any], rank: int) -> ExternalCitation:
    citation = candidate.get("citation", {})
    quote = candidate.get("text", "").strip()
    if len(quote) > 900:
        quote = quote[:897].rsplit(" ", 1)[0] + "..."

    source = CitationSource(
        title=citation.get("title") or candidate.get("title", ""),
        url=citation.get("url") or candidate.get("url", ""),
        citation_label=citation.get("citation_label") or candidate.get("title", ""),
        source_type=citation.get("source_type") or candidate.get("source_type", "OTHER"),
        effective_date=citation.get("effective_date"),
    )

    return ExternalCitation(
        citation_id=f"ext-cite-{rank:03d}",
        source_type=candidate.get("source_type", "OTHER"),
        title=candidate.get("title", ""),
        url=candidate.get("url"),
        document_id=candidate.get("source_id"),
        quote=quote,
        matched_codes=candidate.get("codes", []),
        matched_terms=candidate.get("_matched_terms", []),
        relevance_score=max(0.0, min(candidate.get("_score", 0.0), 1.0)),
        authority_score=max(0.0, min(candidate.get("_authority_score", 0.0), 1.0)),
        citation=source,
    )


def retrieve_external_evidence(task: ExternalEvidenceTask, top_k: int = 8) -> ExternalEvidenceArtifact:
    store = MongoEvidenceStore()
    queries = build_queries(task, top_k=top_k)
    traces: list[QueryTrace] = []
    merged: dict[str, dict[str, Any]] = {}

    for query in queries:
        results = store.search(query)
        traces.append(
            QueryTrace(
                query=query.query,
                strategy=query.strategy,
                top_k=query.top_k,
                result_count=len(results),
            )
        )
        for result in results:
            key = result.get("chunk_id") or f"{result.get('source_id')}:{result.get('chunk_index')}"
            if key not in merged or result["_score"] > merged[key]["_score"]:
                merged[key] = result

    ranked = diversify_results(sorted(merged.values(), key=lambda result: result["_score"], reverse=True), top_k)
    citations = [candidate_to_citation(candidate, index + 1) for index, candidate in enumerate(ranked)]
    evidence_gaps = []
    if not citations:
        evidence_gaps.append(
            {
                "gap_type": "no_retrieval_results",
                "message": "No citation-backed evidence chunks matched the task.",
            }
        )

    codes = extract_codes(task)
    summary = coverage_summary(citations, codes, task.insurer)
    status = "success" if citations else "partial"

    return ExternalEvidenceArtifact(
        case_id=task.case_id,
        schema_version=task.schema_version,
        status=status,
        provenance={
            "agent": "external_evidence_agent",
            "retrieval_mode": "metadata_lexical_mongo",
            "generated_at": utc_now(),
        },
        data=ExternalEvidenceData(
            source_task_ref="external_evidence_task",
            query_traces=traces,
            citations=citations,
            source_coverage_summary=summary,
            evidence_gaps=evidence_gaps,
            notes_for_strategy_agent=[
                "Retrieved evidence is citation-backed from the curated MongoDB corpus.",
                "Embeddings/vector search are not enabled yet; ranking uses metadata and lexical scoring.",
            ],
        ),
    )


def coverage_summary(citations: list[ExternalCitation], codes: list[str], insurer: str | None) -> str:
    if not citations:
        return "No curated external evidence was found for this task."

    source_counts = Counter(citation.source_type for citation in citations)
    code_text = ", ".join(codes) if codes else "the denied service"
    insurer_text = f" and {insurer} policy" if insurer else ""
    parts = [f"Found {len(citations)} citation-backed chunks for {code_text}{insurer_text}."]
    parts.extend(f"{source_type}: {count}" for source_type, count in sorted(source_counts.items()))
    return " ".join(parts)


def diversify_results(results: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    source_counts: Counter[str] = Counter()
    source_type_counts: Counter[str] = Counter()

    for result in results:
        source_id = result.get("source_id", "unknown")
        source_type = result.get("source_type", "OTHER")
        if source_counts[source_id] >= 2:
            continue
        if source_type_counts[source_type] >= 3:
            continue
        selected.append(result)
        source_counts[source_id] += 1
        source_type_counts[source_type] += 1
        if len(selected) == top_k:
            return selected

    selected_ids = {result.get("chunk_id") for result in selected}
    for result in results:
        if result.get("chunk_id") in selected_ids:
            continue
        selected.append(result)
        if len(selected) == top_k:
            return selected

    return selected


def load_task(path: Path) -> ExternalEvidenceTask:
    return ExternalEvidenceTask.model_validate_json(path.read_text(encoding="utf-8"))
