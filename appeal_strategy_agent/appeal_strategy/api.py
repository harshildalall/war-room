"""FastAPI app for the Appeal Strategy Agent.

Exposes POST /strategy, which accepts the four upstream agent payloads
(denial_intake, personal_evidence, external_evidence, contact_actions) and
returns the structured strategy.

A tolerant parser layer (parse_input) normalizes loose inputs from upstream
agents BEFORE Pydantic validation runs, so minor schema drift (string vs.
list, null vs. empty string, stringified numbers, missing optional fields)
doesn't cause a hard reject. Strict types are still enforced internally
once the request reaches the strategy engine.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from appeal_strategy.strategy_engine import (
    StrategyEngineError,
    generate_strategy,
)

logger = logging.getLogger("appeal_strategy.api")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)


class DenialIntake(BaseModel):
    model_config = ConfigDict(extra="allow")

    case_id: str
    insurer: str
    plan_id: str
    member_id: str
    denied_procedure_codes: list[str]
    diagnosis_codes: list[str]
    denial_reason_text: str
    denial_reason_category: str
    denial_date: str
    appeal_deadline: str
    appeal_level: str
    treating_physician: str
    service_dates: list[str]
    confidence_score: float


class PersonalEvidence(BaseModel):
    model_config = ConfigDict(extra="allow")

    case_id: str
    symptoms: list[str]
    treatment_history: list[dict[str, Any]]
    prior_treatment_attempts: list[dict[str, Any]]
    treating_physician_statement: str
    evidence_strength_score: float
    gaps_found: list[str]


class ExternalEvidence(BaseModel):
    model_config = ConfigDict(extra="allow")

    case_id: str
    citations: list[dict[str, Any]]
    guidelines_found: list[str]
    cms_ncd_references: list[str]
    evidence_strength_score: float


class ContactActions(BaseModel):
    model_config = ConfigDict(extra="allow")

    case_id: str
    actions_taken: list[str]
    supplemental_sources: list[dict[str, Any]] = Field(default_factory=list)
    outreach_status: str
    additional_docs_retrieved: list[str]


class StrategyRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    denial_intake: DenialIntake
    personal_evidence: PersonalEvidence
    external_evidence: ExternalEvidence
    contact_actions: ContactActions


# --- tolerant parser -------------------------------------------------------

# Per-object schema spec used by parse_input(). Lists which fields should be
# coerced into which shapes when upstream sends loose data.
FIELD_SPECS: dict[str, dict[str, Any]] = {
    "denial_intake": {
        "list_str": [
            "denied_procedure_codes",
            "diagnosis_codes",
            "service_dates",
        ],
        "list_dict": [],
        "str": [
            "case_id",
            "insurer",
            "plan_id",
            "member_id",
            "denial_reason_text",
            "denial_reason_category",
            "denial_date",
            "appeal_deadline",
            "appeal_level",
            "treating_physician",
        ],
        "float": ["confidence_score"],
        "aliases": {"procedure_codes": "denied_procedure_codes"},
        "defaults": {"treating_physician": "Not specified"},
    },
    "personal_evidence": {
        "list_str": ["symptoms", "gaps_found"],
        "list_dict": ["treatment_history", "prior_treatment_attempts"],
        "str": ["case_id", "treating_physician_statement"],
        "float": ["evidence_strength_score"],
        "aliases": {},
        "defaults": {},
    },
    "external_evidence": {
        "list_str": ["guidelines_found", "cms_ncd_references"],
        "list_dict": ["citations"],
        "str": ["case_id"],
        "float": ["evidence_strength_score"],
        "aliases": {},
        "defaults": {},
    },
    "contact_actions": {
        "list_str": ["actions_taken", "additional_docs_retrieved"],
        "list_dict": ["supplemental_sources"],
        "str": ["case_id", "outreach_status"],
        "float": [],
        "aliases": {},
        "defaults": {},
    },
}


def _normalize_object(
    section: str, obj: Any, warnings: list[str]
) -> dict[str, Any]:
    """Normalize a single top-level section (e.g. denial_intake) in place-style.

    Returns a new dict; appends human-readable strings to `warnings` describing
    what was changed.
    """
    if obj is None:
        warnings.append(f"{section} was null; replaced with empty object")
        obj = {}
    if not isinstance(obj, dict):
        # Can't recover — leave as-is so Pydantic produces a clean error.
        return obj

    spec = FIELD_SPECS.get(section)
    if spec is None:
        return dict(obj)

    out = dict(obj)

    # Aliases first, so the canonical name is the one we coerce.
    for alias, canonical in spec["aliases"].items():
        if canonical not in out and alias in out:
            out[canonical] = out.pop(alias)
            warnings.append(
                f"{section}.{alias} aliased to {canonical}"
            )

    # list[str] fields: wrap singleton string, drop nulls, coerce items to str.
    for field in spec["list_str"]:
        if field not in out:
            continue
        v = out[field]
        if v is None:
            out[field] = []
            warnings.append(
                f"Normalized {section}.{field} from null to empty list"
            )
        elif isinstance(v, str):
            out[field] = [v]
            warnings.append(
                f"Normalized {section}.{field} from string to list"
            )
        elif isinstance(v, (int, float)):
            out[field] = [str(v)]
            warnings.append(
                f"Normalized {section}.{field} from {type(v).__name__} "
                "to list[str]"
            )
        elif isinstance(v, list):
            coerced = [str(x) if not isinstance(x, str) else x for x in v if x is not None]
            if coerced != v:
                out[field] = coerced
                warnings.append(
                    f"Normalized {section}.{field} list items to str / "
                    "stripped nulls"
                )

    # list[dict] fields: wrap singleton dict, drop nulls.
    for field in spec["list_dict"]:
        if field not in out:
            continue
        v = out[field]
        if v is None:
            out[field] = []
            warnings.append(
                f"Normalized {section}.{field} from null to empty list"
            )
        elif isinstance(v, dict):
            out[field] = [v]
            warnings.append(
                f"Normalized {section}.{field} from object to list[object]"
            )

    # str fields: null → "".
    for field in spec["str"]:
        if field in out and out[field] is None:
            out[field] = ""
            warnings.append(
                f"Normalized {section}.{field} from null to empty string"
            )

    # float fields: stringified numbers → float.
    for field in spec["float"]:
        if field not in out:
            continue
        v = out[field]
        if isinstance(v, str):
            try:
                out[field] = float(v)
                warnings.append(
                    f"Normalized {section}.{field} from string to float"
                )
            except ValueError:
                # Leave as-is; Pydantic will surface a clear error.
                pass
        elif v is None:
            out[field] = 0.0
            warnings.append(
                f"Normalized {section}.{field} from null to 0.0"
            )

    # Defaults for missing/null required-ish string fields.
    for field, default in spec["defaults"].items():
        if field not in out or out[field] in (None, ""):
            out[field] = default
            warnings.append(
                f"Defaulted {section}.{field} to {default!r}"
            )

    return out


def parse_input(raw: Any) -> tuple[dict[str, Any], list[str]]:
    """Normalize a raw request body into the shape StrategyRequest expects.

    Returns (normalized_dict, warnings). `warnings` is a list of human-readable
    strings describing every change made; callers can log it to surface which
    upstream agent is sending loose data.
    """
    warnings: list[str] = []
    if not isinstance(raw, dict):
        return raw, warnings

    out = dict(raw)
    for section in FIELD_SPECS:
        if section in out:
            out[section] = _normalize_object(section, out[section], warnings)

    return out, warnings


def _validate_or_400(normalized: dict[str, Any]) -> StrategyRequest:
    try:
        return StrategyRequest.model_validate(normalized)
    except ValidationError as e:
        bad_fields = sorted(
            {".".join(str(p) for p in err["loc"]) for err in e.errors()}
        )
        raise HTTPException(
            status_code=400,
            detail={
                "message": (
                    "Input failed validation even after normalization. "
                    "Fix the listed fields in the upstream agent output."
                ),
                "invalid_fields": bad_fields,
                "errors": e.errors(),
            },
        ) from e


# --- app -------------------------------------------------------------------

app = FastAPI(title="Counterclaim — Appeal Strategy Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/strategy")
async def strategy(request: Request) -> dict[str, Any]:
    raw = await request.json()
    normalized, warnings = parse_input(raw)

    if warnings:
        logger.warning(
            "parse_input normalized %d field(s): %s",
            len(warnings),
            "; ".join(warnings),
        )

    req = _validate_or_400(normalized)

    try:
        result = generate_strategy(
            req.denial_intake.model_dump(),
            req.personal_evidence.model_dump(),
            req.external_evidence.model_dump(),
            req.contact_actions.model_dump(),
        )
    except StrategyEngineError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    return {
        "case_id": req.denial_intake.case_id,
        "status": "success",
        "strategy": result,
        "normalization_warnings": warnings,
    }


@app.post("/strategy/validate")
async def strategy_validate(request: Request) -> dict[str, Any]:
    """Run parse_input + Pydantic validation only. No model call.

    Lets upstream-agent owners check whether their output will be accepted,
    and see what the parser rewrote, without burning an LLM call.
    """
    raw = await request.json()
    normalized, warnings = parse_input(raw)

    if warnings:
        logger.warning(
            "parse_input (validate) normalized %d field(s): %s",
            len(warnings),
            "; ".join(warnings),
        )

    try:
        StrategyRequest.model_validate(normalized)
    except ValidationError as e:
        bad_fields = sorted(
            {".".join(str(p) for p in err["loc"]) for err in e.errors()}
        )
        return {
            "status": "invalid",
            "normalization_warnings": warnings,
            "invalid_fields": bad_fields,
            "errors": e.errors(),
            "normalized_input": normalized,
        }

    return {
        "status": "valid",
        "normalization_warnings": warnings,
        "normalized_input": normalized,
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("appeal_strategy.api:app", host="0.0.0.0", port=8001, reload=True)
