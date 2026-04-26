from __future__ import annotations

import re

from schemas import EvidenceQuery, ExternalEvidenceTask, SourceType


CODE_PATTERN = re.compile(r"\b(?:[A-Z]\d{4}|\d{5})\b")

PREFERRED_SOURCE_MAP: dict[str, SourceType] = {
    "CMS NCD": "CMS_NCD",
    "CMS LCD": "CMS_LCD",
    "LCD": "CMS_LCD",
    "CMS manual": "CMS_MANUAL",
    "PubMed": "SPECIALTY_GUIDELINE",
    "specialty society guidelines": "SPECIALTY_GUIDELINE",
    "insurer policy": "INSURER_POLICY",
}


def extract_codes(task: ExternalEvidenceTask) -> list[str]:
    found: list[str] = []

    for values in task.codes.values():
        found.extend(values)
    found.extend(task.denied_procedures)
    for query in task.search_queries:
        found.extend(CODE_PATTERN.findall(query))

    normalized: list[str] = []
    for code in found:
        code = code.strip().upper()
        if code and code not in normalized:
            normalized.append(code)
    return normalized


def preferred_source_types(task: ExternalEvidenceTask) -> list[SourceType]:
    mapped: list[SourceType] = []
    for preferred in task.preferred_sources:
        for key, source_type in PREFERRED_SOURCE_MAP.items():
            if key.lower() in preferred.lower() and source_type not in mapped:
                mapped.append(source_type)

    for source_type in ["INSURER_POLICY", "CMS_LCD", "CMS_MANUAL"]:
        if source_type not in mapped:
            mapped.append(source_type)  # type: ignore[arg-type]
    return mapped


def build_queries(task: ExternalEvidenceTask, top_k: int = 8) -> list[EvidenceQuery]:
    codes = extract_codes(task)
    source_types = preferred_source_types(task)
    queries: list[EvidenceQuery] = []

    for code in codes:
        queries.append(
            EvidenceQuery(
                query=code,
                strategy="exact_code",
                top_k=top_k,
                codes=[code],
                source_types=source_types,
                insurer=task.insurer,
            )
        )

    if task.insurer:
        insurer_terms = " ".join([task.insurer, task.denial_category or "", *task.search_queries[:2]])
        queries.append(
            EvidenceQuery(
                query=insurer_terms.strip(),
                strategy="policy_lookup",
                top_k=top_k,
                codes=codes,
                source_types=["INSURER_POLICY"],
                insurer=task.insurer,
            )
        )

    for query in task.search_queries:
        queries.append(
            EvidenceQuery(
                query=query,
                strategy="hybrid",
                top_k=top_k,
                codes=codes,
                source_types=source_types,
                insurer=task.insurer,
            )
        )

    if task.denial_category:
        queries.append(
            EvidenceQuery(
                query=f"{task.denial_category} physical therapy rehabilitation therapeutic exercise medical necessity",
                strategy="semantic",
                top_k=top_k,
                codes=codes,
                source_types=source_types,
                insurer=task.insurer,
            )
        )

    return dedupe_queries(queries)


def dedupe_queries(queries: list[EvidenceQuery]) -> list[EvidenceQuery]:
    seen: set[tuple[str, str]] = set()
    deduped: list[EvidenceQuery] = []
    for query in queries:
        key = (query.strategy, query.query.lower())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(query)
    return deduped
