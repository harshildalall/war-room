from __future__ import annotations

import json
import re
import sys
import threading
from pathlib import Path
from typing import Any
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Body, File, Form, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles


REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = REPO_ROOT / "frontend"
CASES_DIR = REPO_ROOT / "cases"
DEFAULT_CASE_PATH = REPO_ROOT / "orchestrator" / "golden_cases" / "pt_tibia_rehab_case.json"

sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "contact_agent"))
sys.path.insert(0, str(REPO_ROOT / "external_evidence_agent"))
sys.path.insert(0, str(REPO_ROOT / "appeal_strategy_agent"))
sys.path.insert(0, str(REPO_ROOT / "drafting_agent"))

load_dotenv(REPO_ROOT / "external_evidence_agent" / ".env")

from orchestrator.run_pipeline import load_json, run_pipeline
from parser.classify import classify_file
from parser.prompt import run_parser_prompt

app = FastAPI(title="Counterclaim Demo Backend")
JOBS: dict[str, dict[str, Any]] = {}
JOBS_LOCK = threading.Lock()


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Missing artifact: {path.name}")
    return json.loads(path.read_text(encoding="utf-8"))


def artifacts_dir(case_id: str) -> Path:
    return CASES_DIR / case_id / "artifacts"


def build_case_payload(case_id: str) -> dict[str, Any]:
    base = artifacts_dir(case_id)
    result_path = CASES_DIR / case_id / "pipeline_result.json"
    if not result_path.exists():
        raise HTTPException(status_code=404, detail="No generated case result found.")

    return {
        "pipeline_result": read_json(result_path),
        "drafted_letter": read_json(base / "drafted_letter.json"),
        "appeal_packet": read_json(base / "appeal_packet.json"),
        "appeal_strategy": read_json(base / "appeal_strategy.json"),
        "verification_report": read_json(base / "verification_report.json"),
        "external_evidence": read_json(base / "external_evidence.json"),
    }


def demo_case_with_preferences(preferences: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = load_json(DEFAULT_CASE_PATH)
    if preferences:
        payload["user_preferences"] = preferences
    return payload


def _decode_pdf_text_without_fitz(file_bytes: bytes) -> str:
    """Tiny fallback for text-based PDFs when PyMuPDF is not installed."""
    chunks: list[str] = []
    for raw in re.findall(rb"\((.*?)\)\s*Tj", file_bytes, flags=re.S):
        text = raw.decode("latin-1", errors="ignore")
        text = text.replace(r"\(", "(").replace(r"\)", ")").replace(r"\\", "\\")
        chunks.append(text)
    return "\n".join(chunks).strip()


def extract_uploaded_text(file_bytes: bytes, content_type: str) -> str:
    if content_type == "text/plain":
        return file_bytes.decode("utf-8", errors="ignore").strip()
    if content_type == "application/pdf":
        try:
            import fitz  # type: ignore

            doc = fitz.open(stream=file_bytes, filetype="pdf")
            return "\n".join(page.get_text() for page in doc).strip()
        except ModuleNotFoundError:
            return _decode_pdf_text_without_fitz(file_bytes)
    return ""


def parsed_case_to_pipeline_input(
    parsed: dict[str, Any],
    preferences: dict[str, Any] | None = None,
    patient_narrative: str | None = None,
) -> dict[str, Any]:
    golden = demo_case_with_preferences()
    case_id = parsed.get("case_id") or parsed.get("denial_intake", {}).get("case_id") or str(uuid4())
    denial = parsed.get("denial_intake", {})
    codes = denial.get("codes", {}) if isinstance(denial.get("codes"), dict) else {}
    cpt_codes = codes.get("cpt_hcpcs") or denial.get("denied_procedure_codes") or []
    diagnosis_codes = codes.get("icd10") or denial.get("diagnosis_codes") or []
    insurer = denial.get("insurer") or denial.get("insurer_name") or golden["denial_intake"].get("insurer")
    plan_id = denial.get("plan_id") or denial.get("plan_name") or golden["denial_intake"].get("plan_id", "")
    member_id = denial.get("member_id") or denial.get("member_id_last4") or golden["denial_intake"].get("member_id", "")

    pipeline_denial = {
        **golden["denial_intake"],
        **denial,
        "case_id": case_id,
        "insurer": insurer,
        "plan_id": plan_id,
        "member_id": member_id,
        "denied_procedure_codes": cpt_codes,
        "diagnosis_codes": diagnosis_codes,
        "denial_reason_text": denial.get("denial_reason_text") or golden["denial_intake"].get("denial_reason_text", ""),
        "denial_reason_category": denial.get("denial_reason_category") or "other",
        "appeal_level": denial.get("appeal_level") or denial.get("current_appeal_level") or "first_internal",
        "treating_physician": denial.get("treating_physician") or golden["denial_intake"].get("treating_physician", "Not specified"),
        "service_dates": denial.get("service_dates") or golden["denial_intake"].get("service_dates", []),
        "confidence_score": denial.get("confidence_score")
        or max((denial.get("field_confidence") or {}).values(), default=0.72),
    }

    external_task = parsed.get("external_evidence_task", {})
    pipeline_external_task = {
        **golden["external_evidence_task"],
        **external_task,
        "case_id": case_id,
        "insurer": external_task.get("insurer") or external_task.get("insurer_name") or insurer,
        "denied_procedures": external_task.get("denied_procedures") or cpt_codes,
        "diagnosis": external_task.get("diagnosis") or diagnosis_codes,
        "codes": external_task.get("codes") or {"cpt_hcpcs": cpt_codes, "icd10": diagnosis_codes},
    }

    personal_evidence = {
        **golden["personal_evidence"],
        "case_id": case_id,
        "provenance": {"source": "uploaded_denial_with_demo_patient_facts", "contains_phi": False},
    }
    if patient_narrative:
        personal_evidence["patient_narrative"] = patient_narrative

    payload = {
        "case_id": case_id,
        "denial_intake": pipeline_denial,
        "missing_info_request": {**golden["missing_info_request"], **parsed.get("missing_info_request", {}), "case_id": case_id},
        "personal_evidence_task": {**golden.get("personal_evidence_task", {}), **parsed.get("personal_evidence_task", {}), "case_id": case_id},
        "personal_evidence": personal_evidence,
        "external_evidence_task": pipeline_external_task,
    }
    if preferences:
        payload["user_preferences"] = preferences
    if patient_narrative:
        payload["patient_narrative"] = patient_narrative
    return payload


def set_job(job_id: str, **updates: Any) -> None:
    with JOBS_LOCK:
        current = JOBS.setdefault(job_id, {})
        current.update(updates)


def append_job_event(job_id: str, event: dict[str, Any]) -> None:
    with JOBS_LOCK:
        current = JOBS.setdefault(job_id, {})
        current.setdefault("events", []).append(event)
        current["latest_event"] = event


def run_job(job_id: str, preferences: dict[str, Any] | None = None) -> None:
    set_job(job_id, status="running", result=None, error=None)
    try:
        result = run_pipeline(
            demo_case_with_preferences(preferences),
            status_callback=lambda event: append_job_event(job_id, event),
        )
        set_job(job_id, status="success", result=build_case_payload(result["case_id"]))
    except Exception as exc:
        append_job_event(
            job_id,
            {
                "step": "pipeline",
                "status": "failed",
                "artifact": None,
                "notes": [f"{type(exc).__name__}: {exc}"],
            },
        )
        set_job(job_id, status="failed", error=f"{type(exc).__name__}: {exc}")


def run_uploaded_job(
    job_id: str,
    uploads: list[dict[str, Any]],
    preferences: dict[str, Any] | None = None,
    patient_narrative: str | None = None,
) -> None:
    set_job(job_id, status="running", result=None, error=None)
    try:
        append_job_event(
            job_id,
            {
                "step": "doc_parser_agent",
                "status": "running",
                "artifact": None,
                "notes": ["Extracting text from uploaded denial document"],
            },
        )
        labelled_texts: dict[str, str] = {}
        unknown_texts: list[str] = []
        for upload in uploads:
            filename = upload["filename"]
            content_type = upload["content_type"]
            extracted = extract_uploaded_text(upload["bytes"], content_type)
            if not extracted:
                raise ValueError(f"No text could be extracted from {filename}.")
            doc_type = classify_file(filename, content_type)
            if doc_type == "unknown":
                unknown_texts.append(extracted)
            else:
                labelled_texts[doc_type] = "\n\n".join(
                    value for value in [labelled_texts.get(doc_type), extracted] if value
                )
        if unknown_texts:
            labelled_texts["unknown_documents"] = "\n\n".join(unknown_texts)
        if not labelled_texts:
            raise ValueError("No parser-ready text was extracted from uploaded files.")

        parsed = run_parser_prompt(labelled_texts, patient_narrative or "", str(uuid4()))
        parsed["case_id"] = parsed.get("case_id") or parsed.get("denial_intake", {}).get("case_id")
        append_job_event(
            job_id,
            {
                "step": "doc_parser_agent",
                "status": "success",
                "artifact": None,
                "notes": [f"Parsed {', '.join(labelled_texts.keys())}"],
            },
        )
        result = run_pipeline(
            parsed_case_to_pipeline_input(parsed, preferences, patient_narrative),
            status_callback=lambda event: append_job_event(job_id, event),
        )
        set_job(job_id, status="success", result=build_case_payload(result["case_id"]))
    except Exception as exc:
        append_job_event(
            job_id,
            {
                "step": "doc_parser_agent",
                "status": "failed",
                "artifact": None,
                "notes": [f"{type(exc).__name__}: {exc}"],
            },
        )
        set_job(job_id, status="failed", error=f"{type(exc).__name__}: {exc}")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/tweaks-panel.jsx")
def tweaks_panel() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "tweaks-panel.jsx")


@app.post("/api/run-demo")
def run_demo(payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    result = run_pipeline(demo_case_with_preferences(payload.get("user_preferences")))
    return build_case_payload(result["case_id"])


@app.post("/api/run-demo-job")
def run_demo_job(payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    job_id = str(uuid4())
    with JOBS_LOCK:
        JOBS[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "events": [],
            "result": None,
            "error": None,
        }
    thread = threading.Thread(
        target=run_job,
        args=(job_id, payload.get("user_preferences")),
        daemon=True,
    )
    thread.start()
    return {"job_id": job_id, "status": "queued"}


@app.post("/api/run-upload-job")
async def run_upload_job(
    files: list[UploadFile] = File(...),
    patient_narrative: str = Form(""),
    user_preferences: str = Form("{}"),
) -> dict[str, Any]:
    job_id = str(uuid4())
    try:
        preferences = json.loads(user_preferences) if user_preferences else {}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="user_preferences must be valid JSON.")

    uploads = []
    for file in files:
        uploads.append(
            {
                "filename": file.filename or "uploaded_document",
                "content_type": file.content_type or "application/pdf",
                "bytes": await file.read(),
            }
        )

    with JOBS_LOCK:
        JOBS[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "events": [],
            "result": None,
            "error": None,
        }
    thread = threading.Thread(
        target=run_uploaded_job,
        args=(job_id, uploads, preferences, patient_narrative),
        daemon=True,
    )
    thread.start()
    return {"job_id": job_id, "status": "queued"}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found.")
        return dict(job)


@app.get("/api/latest")
def latest() -> dict[str, Any]:
    case_id = "demo-pt-tibia-001"
    return build_case_payload(case_id)


@app.get("/api/latest/letter.txt")
def latest_letter_text() -> PlainTextResponse:
    payload = build_case_payload("demo-pt-tibia-001")
    letter = payload["drafted_letter"].get("appeal_letter", "")
    if not letter:
        raise HTTPException(status_code=404, detail="No appeal letter found.")
    return PlainTextResponse(
        letter,
        headers={"Content-Disposition": "attachment; filename=counterclaim_appeal_letter.txt"},
    )


if FRONTEND_DIR.exists():
    app.mount("/frontend", StaticFiles(directory=FRONTEND_DIR), name="frontend")
