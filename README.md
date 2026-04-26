# Counterclaim

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
