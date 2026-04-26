def classify_file(filename: str, content_type: str) -> str:
    """
    Returns one of: 'denial_letter', 'insurance_contract',
    'medical_records', 'patient_note', 'unknown'
    """
    name = filename.lower()

    if any(k in name for k in ["denial", "eob", "explanation", "reject", "declin"]):
        return "denial_letter"
    if any(k in name for k in ["contract", "policy", "eoc", "evidence_of_coverage", "plan"]):
        return "insurance_contract"
    if any(k in name for k in ["medical", "record", "chart", "clinical", "rx", "prescription", "lab", "doctor"]):
        return "medical_records"
    if any(k in name for k in ["note", "narrative", "statement", "patient"]):
        return "patient_note"

    if content_type == "text/plain":
        return "patient_note"

    return "unknown"