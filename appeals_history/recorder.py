"""
appeal_history.recorder
~~~~~~~~~~~~~~~~~~~~~~~
Writes de-identified appeal data into the appeal_history database.

Two public functions:
    record_appeal()   — called at the end of run_pipeline()
    record_outcome()  — called separately when the insurer responds
"""
from __future__ import annotations

import logging
from datetime import datetime, UTC
from typing import Any

from appeals_history.db import get_collection
from appeals_history.models import build_set_fields, build_outcome_subdoc

log = logging.getLogger(__name__)

VALID_OUTCOME_STATUSES = frozenset({
    "approved",
    "denied",
    "partial_approval",
    "escalated",
    "withdrawn",
    "pending",
})


def record_appeal(
    *,
    case_id: str,
    denial_intake: dict[str, Any],
    external_evidence: dict[str, Any],
    strategy: dict[str, Any],
    drafted: dict[str, Any],
    pipeline_status: str = "success",
    verification_status: str = "unknown",
) -> None:
    """
    Upsert a de-identified appeal record.

    First insert:   recorded_at stamped, outcome initialised to None.
    Re-run:         updated_at refreshed, all pipeline fields updated.
                    recorded_at and outcome are never touched on re-runs.
    """
    set_fields = build_set_fields(
        case_id=case_id,
        denial_intake=denial_intake,
        external_evidence=external_evidence,
        strategy=strategy,
        drafted=drafted,
        pipeline_status=pipeline_status,
        verification_status=verification_status,
    )

    get_collection().update_one(
        {"case_id": case_id},
        {
            "$set": set_fields,
            "$setOnInsert": {
                "recorded_at": datetime.now(UTC),
                "outcome": None,
            },
        },
        upsert=True,
    )
    log.info("appeal_history: upserted  case_id=%s  status=%s", case_id, pipeline_status)


def record_outcome(
    *,
    case_id: str,
    outcome_status: str,
    outcome_notes: str = "",
    days_to_decision: int | None = None,
) -> None:
    """
    Record the insurer's decision once it arrives.

    outcome_status must be one of:
        approved | denied | partial_approval | escalated | withdrawn | pending
    """
    if outcome_status not in VALID_OUTCOME_STATUSES:
        raise ValueError(
            f"outcome_status must be one of {set(VALID_OUTCOME_STATUSES)}, "
            f"got {outcome_status!r}"
        )

    result = get_collection().update_one(
        {"case_id": case_id},
        {"$set": {"outcome": build_outcome_subdoc(
            outcome_status=outcome_status,
            outcome_notes=outcome_notes,
            days_to_decision=days_to_decision,
        )}},
    )

    if result.matched_count == 0:
        log.warning("appeal_history: unknown case_id=%s — outcome not recorded", case_id)
    else:
        log.info(
            "appeal_history: outcome recorded  case_id=%s  status=%s",
            case_id, outcome_status,
        )
