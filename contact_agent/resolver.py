import json
import anthropic

SYSTEM_PROMPT = """
You are an insurance claims assistant. You receive a list of missing fields
from an insurance denial case and do two things:

1. Determine which fields can be resolved from context vs which require
   outreach to the insurer.

2. Draft a professional, concise email to the insurance company requesting
   the missing information needed to process an appeal.

STRICT RULES:
- Do NOT invent claim data, member IDs, or diagnosis codes.
- The email must be written for the patient or their provider to send —
  never imply it is automated.
- Only request the fields listed in missing_fields. Do not ask for anything else.
- Use formal but plain language. No legal jargon.
- Sign the email as "[ Your Name ]" so the patient fills it in before sending.

Return ONLY valid JSON with no preamble or markdown fences matching this schema:
{
  "resolvable_fields": ["field_name"],
  "requires_outreach": ["field_name"],
  "outreach_status": "email_draft_generated",
  "actions_taken": ["<description of what was resolved or attempted>"],
  "supplemental_sources": ["<any sources checked>"],
  "email_draft": {
    "to": "<insurer name> Appeals / Member Services",
    "subject": "<subject line referencing claim number>",
    "body": "<full email body as a single string with \\n for line breaks>"
  }
}
"""

def resolve_missing_info(request: dict) -> dict:
    client = anthropic.Anthropic()

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": (
                "Here is the missing info request from the parser:\n\n"
                + json.dumps(request, indent=2)
            )
        }]
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw)