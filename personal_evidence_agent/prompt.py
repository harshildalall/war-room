import anthropic
import json
import os
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

SYSTEM_PROMPT = """You are a medical insurance patient advocate. You receive text extracted from patient medical records and a task describing what evidence is needed for an insurance appeal.

You MUST return ONLY a JSON object. No preamble, no explanation, no markdown fences. Raw JSON only.

Rules:
- Only extract facts that are explicitly present in the provided documents
- If a fact is not in the documents, set it to null — do not infer or guess
- Quote directly from documents where possible
- evidence_strength_score is 0.0-1.0 based on how much of the required evidence is present
- gaps_found should list what proof_requirements are still missing after reviewing the documents
"""

OUTPUT_SHAPE = {
    "case_id": "",
    "schema_version": "1.0",
    "status": "success",
    "symptoms": [],
    "treatment_history": [],
    "prior_treatment_attempts": [],
    "treating_physician_statement": None,
    "functional_limitations": [],
    "diagnosis_confirmed": None,
    "service_dates": [],
    "evidence_strength_score": 0.0,
    "gaps_found": [],
    "extracted_facts": {},
    "patient_narrative": None
}

def run_evidence_prompt(
    task: dict,
    document_texts: dict,
    patient_narrative: str,
    case_id: str
) -> dict:
    docs_section = ""
    for doc_type, text in document_texts.items():
        if text:
            docs_section += f"\n--- {doc_type.upper()} ---\n{text[:5000]}\n"

    proof_requirements = json.dumps(task.get("proof_requirements", []), indent=2)
    fact_targets = json.dumps(task.get("fact_targets", []), indent=2)

    user_msg = f"""
CASE ID: {case_id}

WHAT WE NEED TO FIND (proof_requirements):
{proof_requirements}

SPECIFIC FACTS TO EXTRACT (fact_targets):
{fact_targets}

PATIENT NARRATIVE:
{patient_narrative or "Not provided"}

UPLOADED DOCUMENTS:
{docs_section or "No documents uploaded"}

Return a JSON object matching this shape exactly, populated only from the documents above:
{json.dumps(OUTPUT_SHAPE, indent=2)}
"""

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
    result["case_id"] = case_id
    result["schema_version"] = "1.0"

    return result