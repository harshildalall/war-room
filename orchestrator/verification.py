from __future__ import annotations

import re
from copy import deepcopy
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


def build_verification_root(
    denial_intake: dict[str, Any],
    personal_evidence: dict[str, Any],
    external_evidence: dict[str, Any],
    contact_actions: dict[str, Any],
    strategy: dict[str, Any],
    drafted: dict[str, Any] | None = None,
    packet: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "denial_intake": denial_intake,
        "personal_evidence": personal_evidence,
        "external_evidence": external_evidence.get("data", external_evidence),
        "contact_actions": contact_actions,
        "appeal_strategy": strategy,
        "drafted_letter": drafted or {},
        "appeal_packet": packet or {},
    }


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


def keep_strategy_claim(claim_result: dict[str, Any]) -> bool:
    return claim_result.get("status") == "traceable"


def keep_contract_violation(violation_result: dict[str, Any]) -> bool:
    return violation_result.get("status") in {"exact_quote", "paraphrase_supported"}


def exact_source_quote(root: dict[str, Any], ref: str | None) -> str:
    ok, resolved, _ = resolve_reference(root, ref or "")
    return quote_text(resolved) if ok else ""


def remap_indices(indices: list[Any], index_map: dict[int, int]) -> list[int]:
    remapped: list[int] = []
    for value in indices:
        if isinstance(value, int) and value in index_map:
            remapped.append(index_map[value])
    return remapped


def filter_strategy_for_drafting(
    strategy: dict[str, Any],
    root: dict[str, Any],
    strategy_claims: list[dict[str, Any]],
    contract_violations: list[dict[str, Any]],
) -> dict[str, Any]:
    filtered = deepcopy(strategy)
    original_arguments = strategy.get("argument_chain", [])
    original_violations = strategy.get("contract_violations", [])

    kept_arguments: list[dict[str, Any]] = []
    excluded_evidence: list[dict[str, Any]] = []
    argument_index_map: dict[int, int] = {}
    claim_results_by_index = {item["claim_index"]: item for item in strategy_claims}

    for old_index, argument in enumerate(original_arguments):
        result = claim_results_by_index.get(old_index, {"status": "needs_review"})
        if keep_strategy_claim(result):
            argument_index_map[old_index] = len(kept_arguments)
            kept_arguments.append(deepcopy(argument))
        else:
            excluded_evidence.append(
                {
                    "source_section": "argument_chain",
                    "original_index": old_index,
                    "status": result.get("status"),
                    "reason": "Claim did not pass pre-draft citation verification.",
                    "removed_item": argument,
                }
            )

    kept_violations: list[dict[str, Any]] = []
    violation_results_by_index = {item["violation_index"]: item for item in contract_violations}
    for old_index, violation in enumerate(original_violations):
        result = violation_results_by_index.get(old_index, {"status": "unsupported"})
        if keep_contract_violation(result):
            cleaned = deepcopy(violation)
            source_quote = exact_source_quote(root, cleaned.get("source"))
            if source_quote:
                cleaned["verified_quote"] = source_quote
            cleaned["verification_status"] = result.get("status")
            kept_violations.append(cleaned)
        else:
            excluded_evidence.append(
                {
                    "source_section": "contract_violations",
                    "original_index": old_index,
                    "status": result.get("status"),
                    "reason": "Contract violation was weak, unsupported, or had an invalid citation.",
                    "removed_item": violation,
                }
            )

    filtered["argument_chain"] = kept_arguments
    filtered["contract_violations"] = kept_violations
    filtered["excluded_evidence"] = excluded_evidence
    filtered["verification_filter"] = {
        "applied_at": utc_now(),
        "arguments_before": len(original_arguments),
        "arguments_after": len(kept_arguments),
        "contract_violations_before": len(original_violations),
        "contract_violations_after": len(kept_violations),
        "excluded_count": len(excluded_evidence),
    }

    for option in filtered.get("remedy_options", []):
        option["supporting_argument_indices"] = remap_indices(
            option.get("supporting_argument_indices", []),
            argument_index_map,
        )

    return filtered


def verify_and_filter_strategy(
    *,
    case_id: str,
    denial_intake: dict[str, Any],
    personal_evidence: dict[str, Any],
    external_evidence: dict[str, Any],
    contact_actions: dict[str, Any],
    strategy: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    root = build_verification_root(
        denial_intake,
        personal_evidence,
        external_evidence,
        contact_actions,
        strategy,
    )
    strategy_claims = verify_strategy_claims(strategy, root)
    contract_violations = verify_contract_violations(strategy, root)
    filtered_strategy = filter_strategy_for_drafting(
        strategy,
        root,
        strategy_claims,
        contract_violations,
    )
    all_items = [*strategy_claims, *contract_violations]
    counts = Counter(item["status"] for item in all_items)
    recommendations = build_recommendations(strategy_claims, contract_violations, [])
    raw_status = verification_status(all_items)

    report = {
        "case_id": case_id,
        "status": filter_stage_status(raw_status, filtered_strategy),
        "raw_verification_status": raw_status,
        "generated_at": utc_now(),
        "stage": "pre_draft_strategy_filter",
        "summary": {
            "strategy_claims": len(strategy_claims),
            "contract_violations": len(contract_violations),
            "status_counts": dict(counts),
            "recommendation_count": len(recommendations),
            "excluded_count": len(filtered_strategy.get("excluded_evidence", [])),
        },
        "strategy_claims": strategy_claims,
        "contract_violations": contract_violations,
        "recommendations": recommendations,
        "filtered_strategy_summary": filtered_strategy["verification_filter"],
    }
    return filtered_strategy, report


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


def filter_stage_status(raw_status: str, filtered_strategy: dict[str, Any]) -> str:
    filter_summary = filtered_strategy.get("verification_filter", {})
    if not filtered_strategy.get("argument_chain"):
        return "blocked"
    if filter_summary.get("excluded_count", 0):
        return "filtered"
    return raw_status


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
    root = build_verification_root(
        denial_intake,
        personal_evidence,
        external_evidence,
        contact_actions,
        strategy,
        drafted,
        packet,
    )

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
