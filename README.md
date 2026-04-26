# Counterclaim ⚖️

**An AI-powered multi-agent pipeline that reads insurance denial letters and writes back.**

Counterclaim takes a denial intake document, fans out to parallel evidence-gathering agents, synthesizes an appeal strategy, and produces a complete, case-specific appeal letter — all without a human touching a keyboard. It is also deployable as an ASI:One-compatible agent on Fetch.ai's Agentverse.

---

## How It Works

 
```
  [ Denial Letter ]
         │
         ▼
      Parser                         structures the raw denial document
         │
         ▼
  ┌──────┴──────┐
  │             │                    ← parallel
  Personal    External
  Evidence    Evidence
  Agent       Agent
  │             │
  └──────┬──────┘
         │
         ▼
  Appeal Strategy Agent              synthesizes denial + all evidence
         │
         ▼
   Drafting Agent                    writes the appeal letter
         │
         ▼
  [ Appeal Letter ]
```

Each agent is an independent FastAPI service. They communicate exclusively via JSON. The orchestrator wires them together end-to-end.

---

## Agents & Ports

| Agent | Port | Input | Output |
|---|---|---|---|
| `parser` | 8001 | Raw denial document | Structured `denial_intake.json` |
| `contact_agent` | 8002 | `missing_info_request.json` | Clarifying questions / resolved fields |
| `personal_evidence_agent` | 8003 | `personal_evidence_task.json` | `personal_evidence.json` |
| `external_evidence_agent` | 8004 | `external_evidence_task.json` | `external_evidence.json` |
| `appeal_strategy_agent` | 8005 | `denial_intake.json` + both evidence JSONs | `appeal_strategy.json` |
| `drafting_agent` | 8006 | `appeal_strategy.json` | Final appeal letter |

---

## Fetch.ai / Agentverse Integration

Counterclaim ships with an ASI:One-compatible coordinator at `fetch_agents/counterclaim_coordinator.py`. It implements the mandatory Agent Chat Protocol and exposes the full pipeline as a discoverable Agentverse workflow.

- **ASI1 Chat Session:** https://asi1.ai/shared-chat/d6a13959-1b64-4e1d-b34c-7335ad570468
- **Agent Profile:** https://agentverse.ai/agents/details/agent1qwv5hzqy6vq4g8srs3d5hjzxjkss9p0tacvmhdkecus8fk55z5rdv6leevj/profile

---

## Quickstart

### 1. Clone & set up

Each agent manages its own virtual environment. Run these steps inside the agent folder you're working on:

```bash
git clone https://github.com/harshildalall/war-room.git
cd war-room/<your_agent_folder>
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Set your API key

```bash
echo 'ANTHROPIC_API_KEY=sk-ant-your_key_here' > .env
```

> Never commit `.env`. It is in `.gitignore` — keep it that way.

### 3. Run your agent

```bash
uvicorn main:app --reload --port <YOUR_PORT>
```

Use the port for your agent from the table above.

### Running the Fetch Coordinator

```bash
cd war-room
cp fetch_agents/.env.example fetch_agents/.env
# Set FETCH_AGENT_SEED to a private seed phrase in fetch_agents/.env
external_evidence_agent/.venv/bin/python fetch_agents/counterclaim_coordinator.py
```

Open the Agentverse Inspector URL printed in the terminal to register the agent. Once registered, it accepts direct chat prompts from ASI:One, e.g.:

```
Run the demo appeal case.
```

---

## JSON Schema Contract

Every JSON message passed between agents **must** include:

```json
{
  "case_id": "string",
  "schema_version": "string",
  "status": "string",
  "provenance": {}
}
```

The canonical source of truth for all schemas is `shared/schemas.py`. Do not modify it without announcing the change in the group chat first.

---

## API Contract

Every agent must expose:

- `POST /run` — accepts the agent's input JSON, returns its output JSON
- `GET /health` — returns `{"status": "ok"}`

---

## Team Rules

- **Never commit `.env`**
- **Never touch another person's agent folder**
- **Never modify `shared/schemas.py` without a group chat announcement**
- Pass JSON between agents — never raw files
- All JSON output must include `case_id`, `schema_version`, `status`, `provenance`

---

## Git Workflow

```bash
git pull origin main        # always pull before starting
git add .
git commit -m "feat: your message"
git push origin main
```

---

## Sample Inputs

The `sample_inputs/` directory contains example JSON files for each agent stage. Use these to test your agent in isolation before plugging into the orchestrator.

---

## Stack

- **Python 3.11+**
- **FastAPI** — agent HTTP servers
- **Anthropic Claude API** — LLM backbone for all reasoning agents
- **uAgents / Fetch.ai** — Agentverse deployment
- **Pydantic** — schema validation via `shared/schemas.py`
