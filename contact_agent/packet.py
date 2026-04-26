def build_contact_packet(request: dict, resolved: dict) -> dict:
    return {
        "case_id":              request["case_id"],
        "schema_version":       "1.0",
        "status":               "complete",
        "outreach_status":      resolved.get("outreach_status", "email_draft_generated"),
        "actions_taken":        resolved.get("actions_taken", []),
        "resolvable_fields":    resolved.get("resolvable_fields", []),
        "requires_outreach":    resolved.get("requires_outreach", []),
        "supplemental_sources": resolved.get("supplemental_sources", []),
        "additional_docs_retrieved": [],
        "email_draft":          resolved.get("email_draft", {}),
    }