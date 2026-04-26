# Counterclaim Coordinator Agent

Counterclaim is an ASI:One-compatible Fetch/uAgents coordinator for health insurance appeal generation.

The agent receives a user request through the Agent Chat Protocol, runs the Counterclaim multi-agent pipeline, and returns a concise appeal packet summary. The local pipeline coordinates document-derived claim data, missing-information outreach, curated external evidence retrieval, appeal strategy generation, drafting, and citation verification.

## What It Does

- Accepts natural language through ASI:One / Agentverse Chat.
- Runs the Counterclaim appeal pipeline from JSON case data or the included demo case.
- Produces a final appeal packet summary with strategy, citations, deadlines, and artifact paths.
- Uses existing specialized agents behind the coordinator:
  - Contact Agent
  - External Evidence Agent
  - Appeal Strategy Agent
  - Drafting Agent
  - Verification layer

## Demo Prompts

Try:

```text
Run the demo appeal case.
```

Or:

```text
Create an appeal for the demo physical therapy denial and summarize the result.
```

For full case execution, paste a JSON object that matches `orchestrator/golden_cases/pt_tibia_rehab_case.json`.

## Agentverse / ASI:One Notes

This agent implements the mandatory Agent Chat Protocol and is intended to be registered with Agentverse so it is discoverable and callable from ASI:One.

