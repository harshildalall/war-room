import anthropic
import json

SYSTEM_PROMPT = """
You are a medical insurance appeals drafter. You receive a structured
appeal strategy and produce a final appeal letter and supporting metadata.

STRICT RULES:
- Do NOT introduce any new facts, diagnoses, or citations beyond what is
  provided in the appeal_strategy JSON.
- Every citation footnoted must come directly from contract_violations,
  denial_linked_to_patient_facts, or denial_linked_to_policy fields.
- Use formal, professional language appropriate for a health insurance appeal.
- Letter structure: date/header → salutation → denial summary →
  argument paragraphs (one per strongest_argument) → remedy request →
  closing + signature block.

Return ONLY valid JSON — no markdown, no preamble — matching this schema exactly:
{
  "appeal_letter": "<full letter as a single string, paragraphs separated by \\n\\n>",
  "citations_footnoted": [
    {
      "footnote_index": 1,
      "source": "<policy section, guideline name, or record type>",
      "quote": "<exact short phrase from the strategy data>",
      "relevance_score": 0.0
    }
  ],
  "exhibits_checklist": [
    {
      "exhibit_label": "Exhibit A",
      "description": "<what this exhibit is>",
      "required": true
    }
  ],
  "submission_instructions": ["<step 1>", "<step 2>"],
  "deadline": "<ISO date string or 'See denial letter'>"
}
"""

DRAFT_TOOL = {
    "name": "submit_appeal_draft",
    "description": "Return the final appeal letter and supporting appeal packet metadata.",
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "appeal_letter": {
                "type": "string",
                "description": "Full appeal letter as one string with paragraphs separated by blank lines.",
            },
            "citations_footnoted": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "footnote_index": {"type": "integer"},
                        "source": {"type": "string"},
                        "quote": {"type": "string"},
                        "relevance_score": {"type": "number"},
                    },
                    "required": ["footnote_index", "source", "quote", "relevance_score"],
                },
            },
            "exhibits_checklist": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "exhibit_label": {"type": "string"},
                        "description": {"type": "string"},
                        "required": {"type": "boolean"},
                    },
                    "required": ["exhibit_label", "description", "required"],
                },
            },
            "submission_instructions": {
                "type": "array",
                "items": {"type": "string"},
            },
            "deadline": {"type": "string"},
        },
        "required": [
            "appeal_letter",
            "citations_footnoted",
            "exhibits_checklist",
            "submission_instructions",
            "deadline",
        ],
    },
}


def draft_letter(strategy: dict) -> dict:
    client = anthropic.Anthropic()

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        tools=[DRAFT_TOOL],
        tool_choice={"type": "tool", "name": "submit_appeal_draft"},
        messages=[{
            "role": "user",
            "content": (
                "Draft the appeal letter from this strategy data only:\n\n"
                + json.dumps(strategy, indent=2)
            )
        }],
    )

    tool_use = next((block for block in response.content if block.type == "tool_use"), None)
    if tool_use is None:
        raise ValueError(f"Drafting model did not return structured tool output. stop_reason={response.stop_reason!r}")
    return dict(tool_use.input)
