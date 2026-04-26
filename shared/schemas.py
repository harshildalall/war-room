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
    "insurer_name": None,
    "plan_name": None,
    "member_id_last4": None,
    "denied_service": None,
    "denial_reason_text": None,
    "denial_reason_category": None,
    "denial_date": None,
    "appeal_deadline": None,
    "current_appeal_level": None,
    "amount_denied_usd": None,
    "cited_policy_names": [],
    "codes": {
        "cpt_hcpcs": [],
        "icd10": [],
        "revenue_codes": [],
        "policy_codes": []
    },
    "extracted_quotes": [],
    "field_confidence": {},
    "info_gaps": []
}

MISSING_INFO_SHAPE = {
    "case_id": "",
    "schema_version": "1.0",
    "status": "pending",
    "provenance": {},
    "missing_items": [],
    "outreach_targets": [],
    "non_blocking": True
}

PERSONAL_EVIDENCE_TASK_SHAPE = {
    "case_id": "",
    "schema_version": "1.0",
    "status": "pending",
    "provenance": {},
    "denial_category": None,
    "denied_service": None,
    "proof_requirements": [],
    "fact_targets": [],
    "user_questions": [],
    "record_types_to_review": []
}

EXTERNAL_EVIDENCE_TASK_SHAPE = {
    "case_id": "",
    "schema_version": "1.0",
    "status": "pending",
    "provenance": {},
    "denial_category": None,
    "codes": {
        "cpt_hcpcs": [],
        "icd10": [],
        "revenue_codes": [],
        "policy_codes": []
    },
    "denied_service": None,
    "insurer_name": None,
    "plan_name": None,
    "search_objectives": [],
    "source_priority": ["CMS_NCD", "CMS_LCD", "CMS_MANUAL", "INSURER_POLICY", "GUIDELINE"]
}