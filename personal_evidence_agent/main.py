from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from dotenv import load_dotenv
import json, os, sys

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

load_dotenv()

from extractor import extract
from prompt import run_evidence_prompt

app = FastAPI(title="Counterclaim Personal Evidence Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

@app.post("/run")
async def run(
    task: str = Form(...),
    patient_narrative: Optional[str] = Form(None),
    files: Optional[List[UploadFile]] = File(None)
):
    try:
        task_data = json.loads(task)
        case_id = task_data.get("case_id", "unknown")

        document_texts = {}
        if files:
            for file in files:
                file_bytes = await file.read()
                extracted = extract(file_bytes, file.content_type or "application/pdf")
                doc_name = file.filename or "uploaded_document"
                document_texts[doc_name] = extracted

        result = run_evidence_prompt(
            task=task_data,
            document_texts=document_texts,
            patient_narrative=patient_narrative or "",
            case_id=case_id
        )

        return {
            "case_id": case_id,
            "status": "success",
            "personal_evidence": result
        }

    except Exception as e:
        return {
            "case_id": task_data.get("case_id", "unknown") if "task_data" in locals() else "unknown",
            "status": "error",
            "error": str(e)
        }

@app.get("/health")
def health():
    return {"status": "ok"}