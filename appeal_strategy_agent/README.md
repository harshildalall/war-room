# Appeal Strategy Agent

Part of **Counterclaim**, a multi-agent system that helps Medicare patients
appeal wrongful insurance denials. This agent ingests a parsed denial case and
produces a structured appeal strategy: which arguments to make, which evidence
to gather, deadlines, and the recommended appeal level.

The agent is built on the Anthropic Claude SDK (`claude-sonnet-4-6`), wrapped
in a FastAPI HTTP service. Fetch.ai uAgent registration will be added on top
of this in a separate step.

## Setup

```bash
cd appeal_strategy_agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in ANTHROPIC_API_KEY
```

Requires Python 3.11+.

## Run the API

```bash
python -m appeal_strategy.api
# or:
uvicorn appeal_strategy.api:app --reload --port 8001
```

Then `POST` to `http://localhost:8001/strategy`.

## Local testing

Each case file under `appeal_strategy/tests/test_cases/` bundles the four
upstream payloads in one JSON object:

```json
{
  "denial_intake":     { "case_id": "...", "...": "..." },
  "personal_evidence": { "case_id": "...", "...": "..." },
  "external_evidence": { "case_id": "...", "...": "..." },
  "contact_actions":   { "case_id": "...", "...": "..." }
}
```

The harness exits non-zero with a clear message if the file is missing,
empty, malformed, or missing one of the four top-level keys.

### Test cases

Three realistic Medicare denial scenarios ship in this repo. They are
designed to span the confidence spectrum so prompt-quality regressions are
visible.

| File                    | Case               | Scenario                                                                                | Target confidence |
|-------------------------|--------------------|-----------------------------------------------------------------------------------------|-------------------|
| `case_01_input.json`    | `CC-2026-001`      | UHC MA cuts off SNF stay after 19 days post-tibial-fracture in a 91 y/o diabetic; MA-vs-NCD parity, Jimmo, and likely algorithmic review | **strong** ~0.75–0.85 |
| `case_02_input.json`    | `CC-2026-002`      | Traditional Medicare denies lumbar MRI for 68 y/o after 6 wks failed PT; LCD criteria largely met but physician letter is thin | **moderate** ~0.50–0.60 |
| `case_03_input.json`    | `CC-2026-003`      | Humana MA denies investigational off-label combo for 72 y/o stage IV NSCLC; no NCD, no NCCN endorsement | **weak** ~0.25–0.35 |

### Running a case

```bash
# Strong case — should recommend full_overturn with high confidence
python -m appeal_strategy.tests.test_local appeal_strategy/tests/test_cases/case_01_input.json

# Moderate case — should likely recommend procedural_remand or partial coverage
python -m appeal_strategy.tests.test_local appeal_strategy/tests/test_cases/case_02_input.json

# Weak case — should output low confidence and flag whether appeal is worth pursuing
python -m appeal_strategy.tests.test_local appeal_strategy/tests/test_cases/case_03_input.json

# Force a fresh model call (bypass .cache/)
SKIP_CACHE=1 python -m appeal_strategy.tests.test_local appeal_strategy/tests/test_cases/case_01_input.json
```

Each run prints the full strategy JSON followed by a short summary line
(`recommended_remedy`, `confidence_score`, argument count, violation count).

## API

### `POST /strategy`

Request body — the four upstream agent payloads, each matching their schemas:

```json
{
  "denial_intake":     { "case_id": "abc-123", "...": "..." },
  "personal_evidence": { "case_id": "abc-123", "...": "..." },
  "external_evidence": { "case_id": "abc-123", "...": "..." },
  "contact_actions":   { "case_id": "abc-123", "...": "..." }
}
```

Response body:

```json
{
  "case_id": "abc-123",
  "status": "success",
  "strategy": { "...": "structured strategy from the model tool call" }
}
```

### `GET /health`

Returns `{"status": "ok"}`.

## Architecture

- **Inputs** — four payloads from upstream agents: `denial_intake` (parser),
  `personal_evidence`, `external_evidence`, `contact_actions`. Each is wrapped
  in its own XML tag inside the user message so the model can address them
  individually.
- **Output** — a structured strategy object whose schema is defined in
  `appeal_strategy/prompts/strategy_tool.json`. The model is forced to emit
  this shape via Anthropic tool use with
  `tool_choice={"type":"tool", "name":"submit_strategy"}`.
- **System prompt** — `appeal_strategy/prompts/system_prompt.txt`, sent with
  `cache_control: {"type": "ephemeral"}` so repeat calls within the cache TTL
  pay reduced input-token cost.
- **Response cache** — every successful call is written to
  `.cache/<md5(all four inputs)>.json`. Re-running the same case is free.
  Bypass by setting `SKIP_CACHE=1`.

## Layout

```
appeal_strategy_agent/
├── appeal_strategy/
│   ├── api.py              # FastAPI app, POST /strategy
│   ├── strategy_engine.py  # Claude call + caching + forced tool output
│   └── prompts/
│       ├── system_prompt.txt
│       └── strategy_tool.json
├── appeal_strategy/tests/
│   ├── test_local.py
│   └── test_cases/
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```
