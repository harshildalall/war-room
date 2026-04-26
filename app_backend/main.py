from __future__ import annotations

import json
import sys
import threading
from pathlib import Path
from typing import Any
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Body
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

from orchestrator.run_pipeline import load_json, run_pipeline


load_dotenv(REPO_ROOT / "external_evidence_agent" / ".env")

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
