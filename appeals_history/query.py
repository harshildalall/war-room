"""
appeal_history.query
~~~~~~~~~~~~~~~~~~~~
Read-side helpers for the appeal_records collection.

All functions return plain dicts — no pymongo internals leak out.
Assumes appeal_history.db.init_db() has been called once at startup.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from appeals_history.db import get_collection

_NO_ID = {"_id": 0}


# ─────────────────────────────────────────────────────────────────────────────
# SINGLE RECORD
# ─────────────────────────────────────────────────────────────────────────────

def get_appeal(case_id: str) -> dict[str, Any] | None:
    """Return the full document for one case, or None if not found."""
    return get_collection().find_one({"case_id": case_id}, _NO_ID)


# ─────────────────────────────────────────────────────────────────────────────
# LIST / FILTER
# ─────────────────────────────────────────────────────────────────────────────

def list_appeals(
    *,
    insurer_name: str | None = None,
    denial_reason_category: str | None = None,
    outcome_status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """
    Paginated list of appeals, newest first.
    insurer_name is a case-insensitive substring match.
    denial_reason_category and outcome_status are exact matches.
    """
    query: dict[str, Any] = {}
    if insurer_name:
        query["insurer_name"] = {"$regex": insurer_name, "$options": "i"}
    if denial_reason_category:
        query["denial_reason_category"] = denial_reason_category
    if outcome_status:
        query["outcome.outcome_status"] = outcome_status

    return list(
        get_collection()
        .find(query, _NO_ID)
        .sort("recorded_at", -1)
        .skip(offset)
        .limit(limit)
    )


def search_by_code(
    *,
    cpt_hcpcs: str | None = None,
    icd10: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Find appeals referencing a specific CPT/HCPCS or ICD-10 code."""
    query: dict[str, Any] = {}
    if cpt_hcpcs:
        query["cpt_hcpcs_codes"] = cpt_hcpcs
    if icd10:
        query["icd10_codes"] = icd10
    if not query:
        return []

    return list(
        get_collection()
        .find(query, _NO_ID)
        .sort("recorded_at", -1)
        .skip(offset)
        .limit(limit)
    )


def appeals_by_date_range(
    *,
    field: str = "denial_date",
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """
    Range query on a date field. Both bounds are inclusive and optional.
    field must be one of: denial_date | appeal_deadline | recorded_at | updated_at
    """
    allowed = {"denial_date", "appeal_deadline", "recorded_at", "updated_at"}
    if field not in allowed:
        raise ValueError(f"field must be one of {allowed}, got {field!r}")

    bounds: dict[str, Any] = {}
    if start:
        bounds["$gte"] = start
    if end:
        bounds["$lte"] = end
    if not bounds:
        return []

    return list(
        get_collection()
        .find({field: bounds}, _NO_ID)
        .sort("recorded_at", -1)
        .skip(offset)
        .limit(limit)
    )


# ─────────────────────────────────────────────────────────────────────────────
# AGGREGATES
# ─────────────────────────────────────────────────────────────────────────────

def stats_by_insurer() -> list[dict[str, Any]]:
    """Appeal counts and outcome breakdown per insurer, sorted by volume."""
    pipeline = [
        {
            "$group": {
                "_id": "$insurer_name",
                "total": {"$sum": 1},
                "approved":         {"$sum": {"$cond": [{"$eq": ["$outcome.outcome_status", "approved"]}, 1, 0]}},
                "partial_approval": {"$sum": {"$cond": [{"$eq": ["$outcome.outcome_status", "partial_approval"]}, 1, 0]}},
                "denied":           {"$sum": {"$cond": [{"$eq": ["$outcome.outcome_status", "denied"]}, 1, 0]}},
                "escalated":        {"$sum": {"$cond": [{"$eq": ["$outcome.outcome_status", "escalated"]}, 1, 0]}},
                "withdrawn":        {"$sum": {"$cond": [{"$eq": ["$outcome.outcome_status", "withdrawn"]}, 1, 0]}},
                "pending": {
                    "$sum": {
                        "$cond": [
                            {"$or": [
                                {"$eq": ["$outcome.outcome_status", "pending"]},
                                {"$eq": ["$outcome", None]},
                            ]},
                            1, 0,
                        ]
                    }
                },
            }
        },
        {"$sort": {"total": -1}},
        {"$project": {
            "_id": 0,
            "insurer_name": "$_id",
            "total": 1,
            "approved": 1, "partial_approval": 1, "denied": 1,
            "escalated": 1, "withdrawn": 1, "pending": 1,
        }},
    ]
    return list(get_collection().aggregate(pipeline))


def common_denial_reasons(*, limit: int = 10) -> list[dict[str, Any]]:
    """Most frequent denial reason categories across all cases."""
    pipeline = [
        {"$group": {"_id": "$denial_reason_category", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": limit},
        {"$project": {"_id": 0, "denial_reason_category": "$_id", "count": 1}},
    ]
    return list(get_collection().aggregate(pipeline))


def most_cited_sources(*, limit: int = 20) -> list[dict[str, Any]]:
    """External evidence sources cited most often across all appeals."""
    pipeline = [
        {"$unwind": "$citations"},
        {"$match": {"citations.source_type": {"$ne": "letter_footnote"}}},
        {
            "$group": {
                "_id": {
                    "citation_label": "$citations.citation_label",
                    "source_type":    "$citations.source_type",
                    "url":            "$citations.url",
                },
                "times_cited":  {"$sum": 1},
                "avg_relevance": {"$avg": "$citations.relevance_score"},
            }
        },
        {"$sort": {"times_cited": -1}},
        {"$limit": limit},
        {"$project": {
            "_id": 0,
            "citation_label": "$_id.citation_label",
            "source_type":    "$_id.source_type",
            "url":            "$_id.url",
            "times_cited": 1,
            "avg_relevance_score": {"$round": ["$avg_relevance", 3]},
        }},
    ]
    return list(get_collection().aggregate(pipeline))


def remedy_distribution() -> list[dict[str, Any]]:
    """How often each recommended remedy appears across all appeal letters."""
    pipeline = [
        {"$group": {"_id": "$letter.recommended_remedy", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$project": {"_id": 0, "recommended_remedy": "$_id", "count": 1}},
    ]
    return list(get_collection().aggregate(pipeline))


def avg_days_to_decision_by_insurer() -> list[dict[str, Any]]:
    """Average days to decision per insurer, for cases where it was recorded."""
    pipeline = [
        {"$match": {"outcome.days_to_decision": {"$ne": None}}},
        {
            "$group": {
                "_id": "$insurer_name",
                "avg_days": {"$avg": "$outcome.days_to_decision"},
                "resolved_count": {"$sum": 1},
            }
        },
        {"$sort": {"avg_days": 1}},
        {"$project": {
            "_id": 0,
            "insurer_name": "$_id",
            "avg_days_to_decision": {"$round": ["$avg_days", 1]},
            "resolved_count": 1,
        }},
    ]
    return list(get_collection().aggregate(pipeline))
