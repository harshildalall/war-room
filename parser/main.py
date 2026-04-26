from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from dotenv import load_dotenv
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from classify import classify_file
from extract import extract
from prompt import run_parser_prompt
from shared.schemas import new_case_id

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

@app.post("/run")
async def parse_documents(
    files: List[UploadFile] = File(...),
    patient_narrative: Optional[str] = Form(None)
):
    case_id = new_case_id()
    labelled_texts = {}
    unknown_texts = []

    for file in files:
        file_bytes = await file.read()
        doc_type = classify_file(file.filename or "", file.content_type or "")
        extracted = extract(file_bytes, file.content_type or "application/pdf")

        if doc_type == "unknown":
            unknown_texts.append(extracted)
        else:
            if doc_type in labelled_texts:
                labelled_texts[doc_type] += "\n\n" + extracted
            else:
                labelled_texts[doc_type] = extracted

    if unknown_texts:
        labelled_texts["unknown_documents"] = "\n\n".join(unknown_texts)

    if not labelled_texts:
        return {"error": "No text could be extracted from the uploaded files", "case_id": case_id}

    try:
        result = run_parser_prompt(labelled_texts, patient_narrative or "", case_id)
        return {
            "case_id": case_id,
            "status": "success",
            **result
        }
    except Exception as e:
        return {
            "case_id": case_id,
            "status": "error",
            "error": str(e)
        }

@app.get("/health")
def health():
    return {"status": "ok"}