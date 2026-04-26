"""
appeal_history.models
~~~~~~~~~~~~~~~~~~~~~
Document builders for the appeal_records collection.

Every document has this shape:

{
    "case_id":                str,           # unique — pipeline case UUID
    "recorded_at":            datetime,      # UTC — first insert only, never overwritten
    "updated_at":             datetime,      # UTC — refreshed on every upsert
    "insurer_name":           str | None,
    "plan_name":              str | None,
    "denial_reason_category": str | None,
    "denial_reason_text":     str | None,
    "denied_service":         str | None,
    "denial_date":            datetime | None,   # BSON Date
    "appeal_deadline":        datetime | None,   # BSON Date
    "appeal_level":           str | None,
    "amount_denied_usd":      float | None,      # None = unknown, not $0
    "cited_policy_names":     list[str],
    "cpt_hcpcs_codes":        list[str],
    "icd10_codes":            list[str],
    "revenue_codes":          list[str],
    "policy_codes":           list[str],
    "pipeline_status":        str | None,
    "verification_status":    str | None,

    "letter": {
        "recommended_remedy":       str | None,
        "recommendation_reasoning": str | None,
        "argument_count":           int,
        "citation_count":           int,
        "contract_violation_count": int,
        "exhibits_checklist":       list[dict],
        "submission_instructions":  list[str],
        "used_fallback_draft":      bool,
        "generation_note":          str | None,
    } | None,

    "arguments": [
        {
            "position":            int,
            "claim":               str | None,
            "legal_basis":         str | None,
            "source":              str | None,
            "contradiction_score": float,
        },
        ...
    ],

    "citations": [
        {
            "source_type":     str | None,    # CMS_NCD | CMS_LCD | GUIDELINE | …
            "citation_label":  str | None,
            "title":           str | None,
            "url":             str | None,
            "relevance_score": float,
            "footnote_index":  int | None,
        },
        ...
    ],

    "outcome": {
        "outcome_status":   str,              # approved | denied | partial_approval |
                                              # escalated | withdrawn | pending
        "outcome_notes":    str | None,
        "days_to_decision": int | None,
        "recorded_at":      datetime,         # UTC — when the outcome was logged
    } | None,
}

PHI POLICY:
  ✗  member names, member IDs (including last-4), DOB, address
  ✗  treating physician names
  ✗  patient symptoms, treatment history, clinical narratives
  ✓  insurer / plan names, denial codes and reason categories
  ✓  CPT/HCPCS, ICD-10, revenue, and policy codes
  ✓  appeal arguments — legal claims and bases only
  ✓  external evidence citations — source, label, URL, relevance
  ✓  recommended remedy and strategic reasoning
  ✓  pipeline / verification status, outcomes
"""
from __future__ import annotations

from datetime import datetime, UTC
from typing import Any


# ─────────────────────────────────────────────────────────────────────────────
# PRIMARY BUILDERS
# ─────────────────────────────────────────────────────────────────────────────

def build_set_fields(
    *,
    case_id: str,
    denial_intake: dict[str, Any],
    external_evidence: dict[str, Any],
    strategy: dict[str, Any],
    drafted: dict[str, Any],
    pipeline_status: str,
    verification_status: str,
) -> dict[str, Any]:
    """
    The full $set payload for an upsert.
    Does not include recorded_at (goes in $setOnInsert) or outcome
    (managed separately via record_outcome).
    """
    codes: dict = denial_intake.get("codes") or {}
    return {
        "case_id": case_id,
        "updated_at": datetime.now(UTC),
        "insurer_name": denial_intake.get("insurer_name"),
        "plan_name": denial_intake.get("plan_name"),
        "denial_reason_category": denial_intake.get("denial_reason_category"),
        "denial_reason_text": denial_intake.get("denial_reason_text"),
        "denied_service": denial_intake.get("denied_service"),
        "denial_date": _to_datetime(denial_intake.get("denial_date")),
        "appeal_deadline": _to_datetime(denial_intake.get("appeal_deadline")),
        "appeal_level": denial_intake.get("current_appeal_level"),
        "amount_denied_usd": _to_float_or_none(denial_intake.get("amount_denied_usd")),
        "cited_policy_names": denial_intake.get("cited_policy_names") or [],
        "cpt_hcpcs_codes": codes.get("cpt_hcpcs") or [],
        "icd10_codes": codes.get("icd10") or [],
        "revenue_codes": codes.get("revenue_codes") or [],
        "policy_codes": codes.get("policy_codes") or [],
        "pipeline_status": pipeline_status,
        "verification_status": verification_status,
        "letter": _build_letter(strategy=strategy, drafted=drafted),
        "arguments": _build_arguments(strategy.get("argument_chain") or []),
        "citations": _build_citations(
            external_evidence,
            drafted.get("citations_footnoted") or [],
        ),
    }


def build_outcome_subdoc(
    *,
    outcome_status: str,
    outcome_notes: str = "",
    days_to_decision: int | None = None,
) -> dict[str, Any]:
    return {
        "outcome_status": outcome_status,
        "outcome_notes": outcome_notes,
        "days_to_decision": days_to_decision,
        "recorded_at": datetime.now(UTC),
    }


# ─────────────────────────────────────────────────────────────────────────────
# SUBDOCUMENT BUILDERS (internal)
# ─────────────────────────────────────────────────────────────────────────────

def _build_letter(
    *,
    strategy: dict[str, Any],
    drafted: dict[str, Any],
) -> dict[str, Any]:
    argument_chain: list = strategy.get("argument_chain") or []
    violations: list = strategy.get("contract_violations") or []
    citations_footnoted: list = drafted.get("citations_footnoted") or []
    return {
        "recommended_remedy": strategy.get("agent_recommended_remedy"),
        "recommendation_reasoning": strategy.get("agent_recommendation_reasoning"),
        "argument_count": len(argument_chain),
        "citation_count": len(citations_footnoted),
        "contract_violation_count": len(violations),
        "exhibits_checklist": drafted.get("exhibits_checklist") or [],
        "submission_instructions": drafted.get("submission_instructions") or [],
        "used_fallback_draft": bool(drafted.get("generation_note")),
        "generation_note": drafted.get("generation_note"),
    }


def _build_arguments(argument_chain: list[dict]) -> list[dict[str, Any]]:
    result = []
    for i, arg in enumerate(argument_chain):
        legal_basis = (
            arg.get("legal_basis")
            or arg.get("basis")
            or arg.get("policy_basis")
            or arg.get("statutory_basis")
        )
        result.append({
            "position": i,
            "claim": arg.get("claim"),
            "legal_basis": legal_basis,
            "source": arg.get("source") or arg.get("argument_type"),
            "contradiction_score": _to_float_or_zero(arg.get("contradiction_score")),
        })
    return result


def _build_citations(
    external_evidence: dict[str, Any],
    citations_footnoted: list[dict],
) -> list[dict[str, Any]]:
    """
    Merges external evidence citations with letter footnotes.
    Deduplicates on citation_label. Citations with no resolvable label
    get a positional fallback key so they are never silently collapsed.
    """
    ev_data: dict = external_evidence.get("data") or {}
    by_key: dict[str, dict] = {}

    for i, raw in enumerate(ev_data.get("citations") or []):
        meta: dict = raw.get("citation") or {}
        label = meta.get("citation_label") or raw.get("title") or None
        key = label or f"__ev_{i}"
        by_key[key] = {
            "source_type": raw.get("source_type"),
            "citation_label": label,
            "title": raw.get("title"),
            "url": meta.get("url"),
            "relevance_score": _to_float_or_zero(raw.get("relevance_score")),
            "footnote_index": None,
        }

    for fn in citations_footnoted:
        label = fn.get("source") or (fn.get("quote") or "")[:80] or None
        if label and label in by_key:
            by_key[label]["footnote_index"] = fn.get("footnote_index")
        else:
            key = label or f"__fn_{fn.get('footnote_index', id(fn))}"
            by_key[key] = {
                "source_type": "letter_footnote",
                "citation_label": label,
                "title": fn.get("quote"),
                "url": None,
                "relevance_score": _to_float_or_zero(fn.get("relevance_score")),
                "footnote_index": fn.get("footnote_index"),
            }

    return list(by_key.values())


# ─────────────────────────────────────────────────────────────────────────────
# TYPE COERCION
# ─────────────────────────────────────────────────────────────────────────────

def _to_datetime(val: Any) -> datetime | None:
    """
    Accepts a datetime (pass-through) or ISO 8601 string.
    Always returns timezone-aware UTC or None — never raises.
    """
    if val is None:
        return None
    if isinstance(val, datetime):
        return val if val.tzinfo else val.replace(tzinfo=UTC)
    if isinstance(val, str) and val.strip():
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(val.strip(), fmt)
                return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
            except ValueError:
                continue
    return None


def _to_float_or_none(val: Any) -> float | None:
    """None stays None — preserves the distinction between $0 denied and unknown amount."""
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _to_float_or_zero(val: Any) -> float:
    """For scores where 0.0 is a meaningful default."""
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0