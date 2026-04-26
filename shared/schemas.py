from datetime import datetime
import uuid

def make_provenance(source_files: list) -> dict:
    return {
        "source_files": source_files,
        "parsed_at": datetime.utcnow().isoformat(),
        "parser_version": "1.0"
    }

def new_case_id() -> str:
    return str(uuid.uuid4())

DENIAL_INTAKE_SHAPE = {
    "case_id": "",
    "schema_version": "1.0",
    "status": "parsed",
    "provenance": {},
    "insurer": None,
    "plan_id": None,
    "member_id": None,
    "denied_procedure_codes": [],
    "diagnosis_codes": [],
    "denial_reason_text": None,
    "denial_reason_category": None,
    "denial_date": None,
    "appeal_deadline": None,
    "appeal_level": "first_internal",
    "treating_physician": None,
    "service_dates": [],
    "confidence_score": 0.0
}

MISSING_INFO_SHAPE = {
    "case_id": "",
    "schema_version": "1.0",
    "status": "pending",
    "provenance": {},
    "missing_fields": [],
    "can_proceed": True
}

PERSONAL_EVIDENCE_TASK_SHAPE = {
    "case_id": "",
    "schema_version": "1.0",
    "status": "pending",
    "provenance": {},
    "denial_category": None,
    "denied_procedures": [],
    "diagnosis": [],
    "patient_narrative": None,
    "evidence_gaps": [],
    "instructions": {
        "extract_symptoms": True,
        "extract_treatment_history": True,
        "flag_gaps": True,
        "priority_fields": ["treating_physician_statement", "prior_treatment_attempts"]
    }
}

EXTERNAL_EVIDENCE_TASK_SHAPE = {
    "case_id": "",
    "schema_version": "1.0",
    "status": "pending",
    "provenance": {},
    "search_queries": [],
    "preferred_sources": ["CMS NCD", "specialty society guidelines", "PubMed"],
    "denial_category": None,
    "insurer": None
}