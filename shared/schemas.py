"""
shared.schemas
~~~~~~~~~~~~~~
Canonical document shapes for every stage of the pipeline.

These are the authoritative contracts between agents.  Every shape is expressed
as a MongoDB document — field names, types, and nesting match exactly what is
written to and read from MongoDB.  When a new field is added to any shape it
must be added here first.

Type legend used in comments:
    str         plain string
    int         integer
    float       float
    bool        boolean
    datetime    Python datetime (timezone-aware UTC) — stored as BSON Date
    list[T]     array of T
    dict        embedded sub-document
    None        BSON null / not yet populated
"""
from __future__ import annotations

from datetime import datetime, UTC
import uuid


# ─────────────────────────────────────────────────────────────────────────────
# PROVENANCE SUB-DOCUMENT
# Embedded in every top-level document.
# ─────────────────────────────────────────────────────────────────────────────

def make_provenance(source_files: list[str]) -> dict:
    """
    {
        source_files:   list[str]   — filenames or artifact paths that produced this doc
        parsed_at:      str         — ISO UTC timestamp of when parsing ran
        parser_version: str
    }
    """
    return {
        "source_files": source_files,
        "parsed_at": datetime.now(UTC).isoformat(),
        "parser_version": "1.0",
    }


def new_case_id() -> str:
    return str(uuid.uuid4())


# ─────────────────────────────────────────────────────────────────────────────
# DENIAL INTAKE
# Collection: denial_intakes  (one document per case)
# Canonical output of parser/main.py.
#
# Orchestrator field-name rules — read THESE keys, not aliases:
#   member_id_last4        NOT "member_id"
#   plan_name              NOT "plan_id"
#   codes.cpt_hcpcs        NOT top-level "denied_procedure_codes"
#   codes.icd10            NOT top-level "diagnosis_codes"
#   field_confidence       NOT "confidence_score"  (this is a dict, not a float)
# ─────────────────────────────────────────────────────────────────────────────

DENIAL_INTAKE_SHAPE = {
    # ── Identity ──────────────────────────────────────────────────────────
    "case_id":              None,       # str       — pipeline case UUID
    "schema_version":       "1.0",      # str
    "status":               "parsed",   # str       — parsed | incomplete | error
    "provenance":           {},         # dict      — see make_provenance()

    # ── Insurer / plan ────────────────────────────────────────────────────
    "insurer_name":         None,       # str | None
    "plan_name":            None,       # str | None  — canonical; do NOT alias as plan_id
    "member_id_last4":      None,       # str | None  — canonical; do NOT alias as member_id

    # ── Denied service ────────────────────────────────────────────────────
    "denied_service":           None,   # str | None
    "denial_reason_text":       None,   # str | None  — verbatim text from the denial letter
    "denial_reason_category":   None,   # str | None  — normalised category label
    "denial_date":              None,   # datetime | None  — UTC BSON Date
    "appeal_deadline":          None,   # datetime | None  — UTC BSON Date
    "current_appeal_level":     None,   # str | None  — e.g. "first", "second", "external"
    "amount_denied_usd":        None,   # float | None

    # ── Policy references ─────────────────────────────────────────────────
    "cited_policy_names":   [],         # list[str]

    # ── Clinical codes (nested sub-document) ──────────────────────────────
    # Orchestrator must unpack from here — do NOT read flat top-level keys.
    "codes": {
        "cpt_hcpcs":        [],         # list[str]
        "icd10":            [],         # list[str]
        "revenue_codes":    [],         # list[str]
        "policy_codes":     [],         # list[str]
    },

    # ── Parser confidence ─────────────────────────────────────────────────
    "extracted_quotes":     [],         # list[str]
    "field_confidence":     {},         # dict[str, float]  — per-field, NOT a scalar
    "info_gaps":            [],         # list[str]
}


# ─────────────────────────────────────────────────────────────────────────────
# MISSING INFO REQUEST
# Collection: missing_info_requests  (one document per case)
# ─────────────────────────────────────────────────────────────────────────────

MISSING_INFO_SHAPE = {
    "case_id":          None,           # str
    "schema_version":   "1.0",          # str
    "status":           "pending",      # str  — pending | resolved | skipped
    "provenance":       {},             # dict

    "missing_items":    [],             # list[str]   — field names or document types missing
    "outreach_targets": [],             # list[str]   — who to contact (role, not name)
    "non_blocking":     True,           # bool  — True = pipeline continues without waiting
}


# ─────────────────────────────────────────────────────────────────────────────
# PERSONAL EVIDENCE TASK  (input to the personal evidence agent)
# Collection: personal_evidence_tasks
# ─────────────────────────────────────────────────────────────────────────────

PERSONAL_EVIDENCE_TASK_SHAPE = {
    "case_id":          None,           # str
    "schema_version":   "1.0",          # str
    "status":           "pending",      # str  — pending | complete | error
    "provenance":       {},             # dict

    "denial_category":          None,   # str | None
    "denied_service":           None,   # str | None
    "proof_requirements":       [],     # list[str]
    "fact_targets":             [],     # list[str]
    "user_questions":           [],     # list[str]
    "record_types_to_review":   [],     # list[str]
}


# ─────────────────────────────────────────────────────────────────────────────
# PERSONAL EVIDENCE ARTIFACT  (output of the personal evidence agent)
# Collection: personal_evidence_artifacts
#
# personal_evidence_agent/main.py returns:
#     { "case_id": ..., "status": ..., "personal_evidence": <this shape> }
#
# strategy_personal_evidence_shape() in the orchestrator reads the keys below
# directly off the "personal_evidence" sub-dict (i.e. the value, not the wrapper).
#
# PHI NOTE: this collection contains clinical content — treat accordingly.
# ─────────────────────────────────────────────────────────────────────────────

PERSONAL_EVIDENCE_ARTIFACT_SHAPE = {
    "case_id":          None,           # str
    "schema_version":   "1.0",          # str
    "status":           "success",      # str  — success | error
    "provenance":       {},             # dict

    "symptoms":                     [],     # list[str]
    "treatment_history":            [],     # list[str | dict]
    "prior_treatment_attempts":     [],     # list[str | dict]
    "treating_physician_statement": None,   # str | None  — physician's words verbatim
    "evidence_strength_score":      0.0,    # float 0.0–1.0
    "gaps_found":                   [],     # list[str]  — missing records / evidence holes
}


# ─────────────────────────────────────────────────────────────────────────────
# EXTERNAL EVIDENCE TASK  (input to the external evidence agent)
# Collection: external_evidence_tasks
#
# The corresponding Pydantic model lives in external_evidence_agent/schemas.py.
# When fields change here, update that model too (see issues_5_and_6_notes.py).
# ─────────────────────────────────────────────────────────────────────────────

EXTERNAL_EVIDENCE_TASK_SHAPE = {
    "case_id":          None,           # str
    "schema_version":   "1.0",          # str
    "status":           "pending",      # str  — pending | complete | error
    "provenance":       {},             # dict

    "denial_category":  None,           # str | None
    "codes": {
        "cpt_hcpcs":        [],         # list[str]
        "icd10":            [],         # list[str]
        "revenue_codes":    [],         # list[str]
        "policy_codes":     [],         # list[str]
    },
    "denied_service":   None,           # str | None
    "insurer_name":     None,           # str | None
    "plan_name":        None,           # str | None
    "search_objectives": [],            # list[str]
    "source_priority":  [               # list[str]  — ordered search preference
        "CMS_NCD",
        "CMS_LCD",
        "CMS_MANUAL",
        "INSURER_POLICY",
        "GUIDELINE",
    ],
}
