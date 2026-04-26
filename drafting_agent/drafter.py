import json
import anthropic

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

def draft_letter(strategy: dict) -> dict:
    client = anthropic.Anthropic()

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": (
                "Draft the appeal letter from this strategy data only:\n\n"
                + json.dumps(strategy, indent=2)
            )
        }],
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw)