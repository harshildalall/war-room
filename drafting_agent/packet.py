def build_packet(strategy: dict, drafted: dict) -> dict:
    return {
        "case_id":                  strategy["case_id"],
        "appeal_letter":            drafted["appeal_letter"],
        "citations_footnoted":      drafted["citations_footnoted"],
        "exhibits_checklist":       drafted["exhibits_checklist"],
        "submission_instructions":  drafted["submission_instructions"],
        "deadline":                 drafted["deadline"],
        "format":                   ["PDF", "DOCX", "JSON"],
    }