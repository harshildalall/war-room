# Counterclaim

## Fetch.ai / Agentverse

Counterclaim includes an ASI:One-compatible Fetch/uAgents coordinator at
`fetch_agents/counterclaim_coordinator.py`.

This agent implements the mandatory Agent Chat Protocol and exposes the local
Counterclaim pipeline as an executable agent workflow. A user can ask it to run
the demo appeal case, or provide full case JSON matching the orchestrator schema.

### Deliverables

- ASI1 Chat Session: https://asi1.ai/shared-chat/d6a13959-1b64-4e1d-b34c-7335ad570468
- Agent Profile: https://agentverse.ai/agents/details/agent1qwv5hzqy6vq4g8srs3d5hjzxjkss9p0tacvmhdkecus8fk55z5rdv6leevj/profile

### Run the Fetch Coordinator

```bash
cd war-room
cp fetch_agents/.env.example fetch_agents/.env
# Edit fetch_agents/.env and set FETCH_AGENT_SEED to a private seed phrase.
external_evidence_agent/.venv/bin/python fetch_agents/counterclaim_coordinator.py
```

Open the Agentverse Inspector URL printed in the terminal and connect/register
the agent with Agentverse. The agent is intended to be discoverable from ASI:One
through Agentverse and supports direct chat requests such as:

```text
Run the demo appeal case.
```

Payment Protocol is not required for this MVP and is not enabled.

## Setup (every teammate does this once)
```bash
git clone https://github.com/harshildalall/war-room.git
cd war-room
cd your_agent_folder
python3 -m venv .venv
source .venv/bin/activate
pip3 install -r requirements.txt
```

## Create your .env file (never commit this)
```bash
echo 'ANTHROPIC_API_KEY=sk-ant-your_key_here' > .env
```

## Run your agent
```bash
uvicorn main:app --reload --port YOUR_PORT
```

## Ports
- parser: 8001
- contact_agent: 8002
- personal_evidence_agent: 8003
- external_evidence_agent: 8004
- appeal_strategy_agent: 8005
- drafting_agent: 8006

## Rules
- Never commit .env
- Never touch another person's folder
- Never change shared/schemas.py without announcing in group chat
- Every JSON output needs case_id, schema_version, status, provenance
- Pass JSON between agents, never raw files
- Your endpoint must be POST /run
- GET /health must return {"status": "ok"}

## Input each agent receives
- contact_agent: missing_info_request.json
- personal_evidence_agent: personal_evidence_task.json
- external_evidence_agent: external_evidence_task.json
- appeal_strategy_agent: denial_intake.json + personal_evidence.json + external_evidence.json
- drafting_agent: appeal_strategy.json

## Git workflow
```bash
git pull origin main   # before starting work
git add .
git commit -m "feat: your message"
git push origin main
```
