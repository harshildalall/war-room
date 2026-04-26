from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from pathlib import Path
import json, os, sys

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

load_dotenv()

from loader import load_missing_info_request
from resolver import resolve_missing_info
from packet import build_contact_packet

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Counterclaim Contact Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

class RunRequest(BaseModel):
    case_id: str
    missing_info_ref: str

@app.post("/run")
async def run(req: RunRequest):
    try:
        request = load_missing_info_request(req.missing_info_ref)
        resolved = resolve_missing_info(request)
        packet = build_contact_packet(request, resolved)

        packet_path = OUTPUT_DIR / f"{req.case_id}_contact_actions.json"
        with open(packet_path, "w") as f:
            json.dump(packet, f, indent=2)

        return {
            "case_id":    req.case_id,
            "status":     "success",
            "artifacts": {
                "contact_actions": str(packet_path)
            },
            "email_draft": packet["email_draft"]
        }

    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health():
    return {"status": "ok"}