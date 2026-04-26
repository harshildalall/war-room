# Counterclaim ⚖️

**An AI-powered multi-agent pipeline that reads insurance denial letters and writes back.**

Counterclaim takes a denial letter, fans out to parallel evidence-gathering agents, synthesizes an appeal strategy, and produces a complete, case-specific appeal letter — all without a human touching a keyboard. It is also deployable as an ASI:One-compatible agent on Fetch.ai's Agentverse.

---

## How It Works

```
  [ Denial Letter / Upload ]
           │
           ▼
    App Backend (8000)          serves the React UI & manages async job queue
           │
           ▼
        Parser                  structures the raw denial document
           │
           ▼
  ┌────────┼────────┐
  │        │        │           ← parallel
Contact  Personal  External
 Agent   Evidence  Evidence
(8002)   (8003)    (8004)
  │        │        │
  └────────┬────────┘
           │
           ▼
  Appeal Strategy Agent (8005)  Claude: synthesizes denial + all evidence
           │
           ▼
    Drafting Agent (8006)       writes the final appeal letter
           │
           ▼
  [ Appeal Letter + Exhibits ]
```

Each agent is an independent FastAPI service. They communicate exclusively via JSON. The orchestrator wires them together end-to-end (via direct imports, not HTTP).

---

## Agents & Ports

| Agent | Port | Endpoint | Input | Output |
|---|---|---|---|---|
| `app_backend` | 8000 | `POST /api/run-demo-job`, `POST /api/run-upload-job` | PDF/TXT uploads or demo trigger | Job events + final artifacts |
| `parser` | 8001 | `POST /run` | Raw denial document | `denial_intake.json` |
| `contact_agent` | 8002 | `POST /run` | `missing_info_request.json` | `contact_actions.json` |
| `personal_evidence_agent` | 8003 | `POST /run` | `personal_evidence_task.json` + optional docs | `personal_evidence.json` |
| `external_evidence_agent` | 8004 | `POST /run` | `external_evidence_task.json` | `external_evidence.json` (MongoDB citations) |
| `appeal_strategy_agent` | 8005 | `POST /strategy` | `denial_intake` + `personal_evidence` + `external_evidence` + `contact_actions` | `appeal_strategy.json` |
| `drafting_agent` | 8006 | `POST /run` | `appeal_strategy.json` | Final appeal letter + exhibits checklist |

---

## Fetch.ai / Agentverse Integration

Counterclaim ships with an ASI:One-compatible coordinator at `fetch_agents/counterclaim_coordinator.py`. It implements the mandatory Agent Chat Protocol and exposes the full pipeline as a discoverable Agentverse workflow.

- **ASI1 Chat Session:**  https://asi1.ai/shared-chat/93bd0964-153c-4a24-8061-a1265b9b5a9d
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

### 3. Run the full system

Start the app backend — it serves the React UI and orchestrates the pipeline:

```bash
cd app_backend
source .venv/bin/activate
uvicorn main:app --reload --port 8000
```

Then open `http://localhost:8000` in your browser.

### 3a. Run an individual agent

```bash
uvicorn main:app --reload --port <YOUR_PORT>
```

Use the port for your agent from the table above. The `appeal_strategy_agent` is the exception — run it with:

```bash
cd appeal_strategy_agent
uvicorn appeal_strategy.api:app --reload --port 8005
```

### Running the Fetch Coordinator

```bash
cd fetch_agents
echo 'FETCH_AGENT_SEED=your_seed_phrase_here' > .env
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

Exception: `appeal_strategy_agent` uses `POST /strategy` and `POST /strategy/validate`.

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
- **Anthropic Claude API (`claude-sonnet-4-6`)** — LLM backbone for parser, strategy, and drafting agents
- **MongoDB** — evidence store (`counterclaim.evidence_chunks`) and appeals history
- **React 18** — frontend UI (served from `app_backend`)
- **PyMuPDF** — PDF text extraction (with regex fallback)
- **uAgents / Fetch.ai** — Agentverse deployment
- **Pydantic** — schema validation via `shared/schemas.py`
