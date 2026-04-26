from __future__ import annotations

from typing import Any


def _display_remedy(remedy: str) -> str:
    labels = {
        "full_overturn": "a full reversal of the denial",
        "partial_approval": "approval of the medically necessary covered services",
        "records_request": "reconsideration after review of the supporting records",
        "external_review": "external review of the denial",
        "external_review_escalation": "external review if the internal appeal is not granted",
        "procedural_remand": "a complete re-review with a documented clinical rationale",
    }
    return labels.get(remedy, remedy.replace("_", " "))


def _clean_sentence(text: Any) -> str:
    value = str(text or "").strip()
    return value.rstrip(".")


def _build_citations(strategy: dict[str, Any]) -> list[dict[str, Any]]:
    citations: list[dict[str, Any]] = []
    seen_quotes: set[str] = set()
    for violation in strategy.get("contract_violations", [])[:5]:
        quote = _clean_sentence(violation.get("clause"))
        if not quote or quote in seen_quotes:
            continue
        seen_quotes.add(quote)
        citations.append(
            {
                "footnote_index": len(citations) + 1,
                "source": violation.get("source", f"contract_violations[{len(citations)}]"),
                "quote": quote,
                "relevance_score": violation.get("contradiction_score", 0.0),
                "_denial_contradicts": violation.get("denial_contradicts", ""),
            }
        )
    return citations


def _policy_paragraphs(strategy: dict[str, Any], citations: list[dict[str, Any]]) -> list[str]:
    paragraphs: list[str] = []
    for citation in citations[:4]:
        clause = _clean_sentence(citation.get("quote"))
        contradiction = _clean_sentence(citation.get("_denial_contradicts"))
        if contradiction:
            paragraphs.append(f"{clause}. {contradiction}. [{citation['footnote_index']}]")
        else:
            paragraphs.append(f"{clause}. [{citation['footnote_index']}]")
    return paragraphs


def draft_letter(strategy: dict[str, Any]) -> dict[str, Any]:
    """Build a conservative appeal draft from citation-backed strategy fields.

    This intentionally avoids free-form LLM prose. The strategy agent may reason
    broadly, but the final appeal letter should only surface evidence that is
    paired with a citation in `contract_violations`.
    """

    case_id = strategy.get("case_id", "unknown")
    remedy = _display_remedy(str(strategy.get("agent_recommended_remedy", "full_overturn")))
    citations = _build_citations(strategy)
    policy_paragraphs = _policy_paragraphs(strategy, citations)

    paragraphs = [
        "To Whom It May Concern:",
        (
            "I am submitting this appeal to request reconsideration of the denied "
            f"services associated with case {case_id}. I respectfully request {remedy}."
        ),
    ]

    if policy_paragraphs:
        paragraphs.extend(policy_paragraphs)
    else:
        paragraphs.append(
            "The available policy evidence supports reconsideration of the denial. "
            "Please review the enclosed coverage materials and patient-specific records."
        )

    paragraphs.append(
        "For these reasons, the denial should be reversed or re-reviewed under the "
        "coverage authorities cited above. Please include the cited policy materials, "
        "the denial notice, and the relevant clinical records in the appeal file."
    )
    paragraphs.append("Sincerely,\n[Patient / Authorized Representative]")

    return {
        "appeal_letter": "\n\n".join(paragraphs),
        "citations_footnoted": [
            {key: value for key, value in citation.items() if not key.startswith("_")}
            for citation in citations
        ],
        "exhibits_checklist": [
            {
                "exhibit_label": "Exhibit A",
                "description": "Denial letter and plan/coverage documents",
                "required": True,
            },
            {
                "exhibit_label": "Exhibit B",
                "description": "Patient-specific medical evidence and treating physician support",
                "required": True,
            },
            {
                "exhibit_label": "Exhibit C",
                "description": "External policy and coverage citations",
                "required": True,
            },
        ],
        "submission_instructions": [
            "Review the generated appeal letter for accuracy before submission.",
            "Attach the cited exhibits and submit through the insurer appeal channel.",
        ],
        "deadline": strategy.get("appeal_deadline") or "See denial letter",
        "generation_note": "Citation-grounded deterministic draft generated from contract_violations.",
    }
