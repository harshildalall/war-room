"""FastAPI app for the Appeal Strategy Agent.

Exposes POST /strategy, which accepts the four upstream agent payloads
(denial_intake, personal_evidence, external_evidence, contact_actions) and
returns the structured strategy.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from appeal_strategy.strategy_engine import (
    StrategyEngineError,
    generate_strategy,
)


class DenialIntake(BaseModel):
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
    case_id: str
    symptoms: list[str]
    treatment_history: list[dict[str, Any]]
    prior_treatment_attempts: list[dict[str, Any]]
    treating_physician_statement: str
    evidence_strength_score: float
    gaps_found: list[str]


class ExternalEvidence(BaseModel):
    case_id: str
    citations: list[dict[str, Any]]
    guidelines_found: list[str]
    cms_ncd_references: list[str]
    evidence_strength_score: float


class ContactActions(BaseModel):
    case_id: str
    actions_taken: list[str]
    supplemental_sources: list[dict[str, Any]] = Field(default_factory=list)
    outreach_status: str
    additional_docs_retrieved: list[str]


class StrategyRequest(BaseModel):
    denial_intake: DenialIntake
    personal_evidence: PersonalEvidence
    external_evidence: ExternalEvidence
    contact_actions: ContactActions


app = FastAPI(title="Counterclaim — Appeal Strategy Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/strategy")
def strategy(req: StrategyRequest) -> dict[str, Any]:
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
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("appeal_strategy.api:app", host="0.0.0.0", port=8001, reload=True)
