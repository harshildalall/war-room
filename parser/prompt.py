import anthropic
import json
import os
from dotenv import load_dotenv
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from shared.schemas import DENIAL_INTAKE_SHAPE, MISSING_INFO_SHAPE, PERSONAL_EVIDENCE_TASK_SHAPE, EXTERNAL_EVIDENCE_TASK_SHAPE, make_provenance

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

SYSTEM_PROMPT = """You are a medical insurance claims analyst. You receive text extracted from insurance documents and return structured JSON.

You MUST return ONLY a JSON object. No preamble, no explanation, no markdown fences. Raw JSON only.

The object has exactly four keys: denial_intake, missing_info_request, personal_evidence_task, external_evidence_task.

Rules:
- denial_reason_category must be one of: medical_necessity, experimental, out_of_network, prior_auth, exhausted_benefits, other
- appeal_level must be one of: first_internal, second_internal, external_review (default to first_internal if not stated)
- All dates must be YYYY-MM-DD format or null
- CPT codes are 5-digit numeric codes (e.g. "97110")
- ICD-10 codes follow the pattern like "S82.101A", "E66.01", "F32.1"
- confidence_score is 0.0-1.0 reflecting how much key info was found
- missing_fields is a list of dicts with keys: field_name, importance (critical/high/medium)
- can_proceed is false only if denial_reason_text OR denied_procedure_codes are completely missing
- search_queries should be 2-3 specific terms for finding clinical guidelines matching the denied procedure and diagnosis
"""

def build_user_message(labelled_texts: dict, patient_narrative: str, case_id: str) -> str:
    parts = [f"CASE ID: {case_id}\n"]

    for doc_type, text in labelled_texts.items():
        if text:
            parts.append(f"--- {doc_type.upper().replace('_', ' ')} ---\n{text[:6000]}\n")

    if patient_narrative:
        parts.append(f"--- PATIENT NARRATIVE ---\n{patient_narrative}\n")

    parts.append(f"""
Return a JSON object with these four keys populated based on the documents above:

denial_intake: {json.dumps(DENIAL_INTAKE_SHAPE, indent=2)}

missing_info_request: {json.dumps(MISSING_INFO_SHAPE, indent=2)}

personal_evidence_task: {json.dumps(PERSONAL_EVIDENCE_TASK_SHAPE, indent=2)}

external_evidence_task: {json.dumps(EXTERNAL_EVIDENCE_TASK_SHAPE, indent=2)}
""")

    return "\n".join(parts)

def run_parser_prompt(labelled_texts: dict, patient_narrative: str, case_id: str) -> dict:
    user_msg = build_user_message(labelled_texts, patient_narrative, case_id)

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}]
    )

    raw = response.content[0].text.strip()

    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    result = json.loads(raw)

    provenance = make_provenance(list(labelled_texts.keys()))

    for key in ["denial_intake", "missing_info_request", "personal_evidence_task", "external_evidence_task"]:
        if key in result:
            result[key]["case_id"] = case_id
            result[key]["provenance"] = provenance

    return result