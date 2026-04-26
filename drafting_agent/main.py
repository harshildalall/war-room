from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from pathlib import Path
import json, os, sys

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

load_dotenv()

from loader import load_strategy
from drafter import draft_letter
from renderer import render_docx, render_pdf
from packet import build_packet

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Counterclaim Drafting Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

class RunRequest(BaseModel):
    case_id: str
    appeal_strategy_ref: str
    output_format: list = ["pdf", "docx", "json"]
    demo_mode: bool = True

@app.post("/run")
async def run(req: RunRequest):
    try:
        strategy = load_strategy(req.appeal_strategy_ref)
        drafted = draft_letter(strategy)

        docx_path = OUTPUT_DIR / f"{req.case_id}_appeal_letter.docx"
        pdf_path  = OUTPUT_DIR / f"{req.case_id}_appeal_letter.pdf"
        packet_path = OUTPUT_DIR / f"{req.case_id}_appeal_packet.json"

        render_docx(strategy, drafted, docx_path)

        if "pdf" in req.output_format:
            render_pdf(docx_path, pdf_path)

        packet = build_packet(strategy, drafted)

        with open(packet_path, "w") as f:
            json.dump(packet, f, indent=2)

        return {
            "case_id": req.case_id,
            "status": "success",
            "artifacts": {
                "appeal_letter_docx": str(docx_path),
                "appeal_letter_pdf":  str(pdf_path),
                "appeal_packet":      str(packet_path)
            }
        }

    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health():
    return {"status": "ok"}
