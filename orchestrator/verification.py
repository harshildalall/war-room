from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, UTC
from typing import Any


REF_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*|\[\d+\])*$")
RISK_WORDS = {
    "covered",
    "coverage",
    "must",
    "obligate",
    "obligates",
    "required",
    "requires",
    "violate",
    "violates",
    "prohibited",
    "entitled",
    "guarantee",
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
    "it",
    "of",
    "or",
    "that",
    "the",
    "this",
    "to",
    "under",
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


def resolve_reference(root: dict[str, Any], ref: str) -> tuple[bool, Any, str | None]:
    if not isinstance(ref, str) or not REF_PATTERN.match(ref):
        return False, None, "invalid_reference_syntax"

    current: Any = root
    parts = re.findall(r"[A-Za-z_][A-Za-z0-9_]*|\[\d+\]", ref)
    traversed = ""
    for part in parts:
        if part.startswith("["):
            index = int(part[1:-1])
            traversed += part
            if not isinstance(current, list):
                return False, None, f"{traversed} expected list"
            if index >= len(current):
                return False, None, f"{traversed} index out of range"
            current = current[index]
            continue

        traversed = f"{traversed}.{part}" if traversed else part
        if not isinstance(current, dict):
            return False, None, f"{traversed} expected object"
        if part not in current:
            return False, None, f"{traversed} missing"
        current = current[part]

    return True, current, None


def quote_text(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("quote", "text", "clause", "treating_physician_statement", "denial_reason_text"):
            if isinstance(value.get(key), str):
                return value[key]
        return " ".join(str(v) for v in value.values() if isinstance(v, (str, int, float)))
    if isinstance(value, list):
        return " ".join(quote_text(item) for item in value)
    return str(value) if value is not None else ""


def overlap_score(claim: str, source: str) -> float:
    claim_tokens = set(tokenize(claim))
    if not claim_tokens:
        return 0.0
    source_tokens = set(tokenize(source))
    return round(len(claim_tokens & source_tokens) / len(claim_tokens), 3)


def quote_status(quote: str, source_text: str) -> str:
    normalized_quote = " ".join(quote.split()).lower()
    normalized_source = " ".join(source_text.split()).lower()
    if normalized_quote and normalized_quote in normalized_source:
        return "exact_quote"

    score = overlap_score(quote, source_text)
    if score >= 0.7:
        return "paraphrase_supported"
    if score >= 0.35:
        return "weak_overlap"
    return "unsupported"


def risk_terms(text: str) -> list[str]:
    tokens = set(tokenize(text))
    return sorted(tokens & RISK_WORDS)


def status_rank(status: str) -> int:
    order = {
        "exact_quote": 0,
        "paraphrase_supported": 1,
        "valid_reference": 1,
        "weak_overlap": 2,
        "unsupported": 3,
        "invalid_reference": 3,
    }
    return order.get(status, 2)


def verify_strategy_claims(strategy: dict[str, Any], root: dict[str, Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for index, argument in enumerate(strategy.get("argument_chain", [])):
        claim = argument.get("claim", "")
        refs = argument.get("supporting_evidence", []) or []
        ref_results = []
        for ref in refs:
            ok, resolved, error = resolve_reference(root, ref)
            source_text = quote_text(resolved)
            score = overlap_score(claim, source_text) if ok else 0.0
            ref_results.append(
                {
                    "ref": ref,
                    "status": "valid_reference" if ok else "invalid_reference",
                    "error": error,
                    "claim_source_overlap": score,
                    "source_preview": source_text[:280],
                }
            )

        invalid_refs = [item for item in ref_results if item["status"] == "invalid_reference"]
        external_scores = [
            item["claim_source_overlap"]
            for item in ref_results
            if item["ref"].startswith("external_evidence.")
        ]
        max_external_overlap = max(external_scores or [0.0])
        terms = risk_terms(claim)
        needs_review = bool(invalid_refs) or (terms and max_external_overlap < 0.35)

        results.append(
            {
                "claim_index": index,
                "claim": claim,
                "status": "needs_review" if needs_review else "traceable",
                "risk_terms": terms,
                "max_external_overlap": max_external_overlap,
                "references": ref_results,
            }
        )
    return results


def verify_contract_violations(strategy: dict[str, Any], root: dict[str, Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for index, violation in enumerate(strategy.get("contract_violations", [])):
        ref = violation.get("source")
        clause = violation.get("clause", "")
        ok, resolved, error = resolve_reference(root, ref)
        source_text = quote_text(resolved)
        status = quote_status(clause, source_text) if ok else "invalid_reference"
        results.append(
            {
                "violation_index": index,
                "source": ref,
                "status": status,
                "error": error,
                "clause": clause,
                "overlap": overlap_score(clause, source_text) if ok else 0.0,
                "source_preview": source_text[:320],
            }
        )
    return results


def verify_draft_footnotes(drafted: dict[str, Any], root: dict[str, Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for footnote in drafted.get("citations_footnoted", []):
        ref = footnote.get("source")
        quote = footnote.get("quote", "")
        ok, resolved, error = resolve_reference(root, ref)
        source_text = quote_text(resolved)
        status = quote_status(quote, source_text) if ok else "invalid_reference"
        results.append(
            {
                "footnote_index": footnote.get("footnote_index"),
                "source": ref,
                "status": status,
                "error": error,
                "quote": quote,
                "overlap": overlap_score(quote, source_text) if ok else 0.0,
                "source_preview": source_text[:320],
            }
        )
    return results


def verification_status(items: list[dict[str, Any]]) -> str:
    statuses = [item.get("status", "needs_review") for item in items]
    if any(status in {"unsupported", "invalid_reference"} for status in statuses):
        return "failed"
    if any(status in {"weak_overlap", "needs_review"} for status in statuses):
        return "needs_review"
    return "verified"


def build_recommendations(
    strategy_claims: list[dict[str, Any]],
    contract_violations: list[dict[str, Any]],
    draft_footnotes: list[dict[str, Any]],
) -> list[str]:
    recommendations: list[str] = []
    for footnote in draft_footnotes:
        if footnote["status"] != "exact_quote":
            recommendations.append(
                f"Footnote {footnote['footnote_index']} is {footnote['status']} against {footnote['source']}."
            )
    for claim in strategy_claims:
        if claim["status"] == "needs_review":
            recommendations.append(
                f"Strategy claim {claim['claim_index']} needs review; risk terms={claim['risk_terms']}."
            )
    for violation in contract_violations:
        if violation["status"] in {"unsupported", "weak_overlap", "invalid_reference"}:
            recommendations.append(
                f"Contract violation {violation['violation_index']} is {violation['status']} against {violation['source']}."
            )
    return recommendations


def verify_pipeline_artifacts(
    *,
    case_id: str,
    denial_intake: dict[str, Any],
    personal_evidence: dict[str, Any],
    external_evidence: dict[str, Any],
    contact_actions: dict[str, Any],
    strategy: dict[str, Any],
    drafted: dict[str, Any],
    packet: dict[str, Any],
) -> dict[str, Any]:
    root = {
        "denial_intake": denial_intake,
        "personal_evidence": personal_evidence,
        "external_evidence": external_evidence.get("data", external_evidence),
        "contact_actions": contact_actions,
        "appeal_strategy": strategy,
        "drafted_letter": drafted,
        "appeal_packet": packet,
    }

    strategy_claims = verify_strategy_claims(strategy, root)
    contract_violations = verify_contract_violations(strategy, root)
    draft_footnotes = verify_draft_footnotes(drafted, root)
    all_items = [*strategy_claims, *contract_violations, *draft_footnotes]
    counts = Counter(item["status"] for item in all_items)
    recommendations = build_recommendations(strategy_claims, contract_violations, draft_footnotes)

    return {
        "case_id": case_id,
        "status": verification_status(all_items),
        "generated_at": utc_now(),
        "summary": {
            "strategy_claims": len(strategy_claims),
            "contract_violations": len(contract_violations),
            "draft_footnotes": len(draft_footnotes),
            "status_counts": dict(counts),
            "recommendation_count": len(recommendations),
        },
        "strategy_claims": strategy_claims,
        "contract_violations": contract_violations,
        "draft_footnotes": draft_footnotes,
        "recommendations": recommendations,
    }
