from __future__ import annotations

import argparse
import json
import os
import sys
from json import JSONDecodeError
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parents[1]
CASES_DIR = REPO_ROOT / "cases"

sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "contact_agent"))
sys.path.insert(0, str(REPO_ROOT / "external_evidence_agent"))
sys.path.insert(0, str(REPO_ROOT / "appeal_strategy_agent"))
sys.path.insert(0, str(REPO_ROOT / "drafting_agent"))

from contact_agent.packet import build_contact_packet
from contact_agent.resolver import resolve_missing_info
from drafting_agent.drafter import draft_letter
from drafting_agent.packet import build_packet
from external_evidence_agent.retrieval import retrieve_external_evidence
from external_evidence_agent.schemas import ExternalEvidenceTask
from orchestrator.verification import verify_pipeline_artifacts
from appeal_strategy.api import parse_input
from appeal_strategy.strategy_engine import generate_strategy


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def ensure_case_id(payload: dict[str, Any]) -> str:
    case_id = payload.get("case_id")
    if not isinstance(case_id, str) or not case_id.strip():
        raise ValueError("Golden case input must include a non-empty case_id.")
    return case_id


def strategy_external_evidence_shape(external_artifact: dict[str, Any]) -> dict[str, Any]:
    data = external_artifact.get("data", {})
    citations = data.get("citations", [])
    return {
        "case_id": external_artifact["case_id"],
        "citations": citations,
        "guidelines_found": [
            citation.get("citation", {}).get("citation_label") or citation.get("title", "")
            for citation in citations
        ],
        "cms_ncd_references": [
            citation.get("citation", {}).get("citation_label") or citation.get("title", "")
            for citation in citations
            if str(citation.get("source_type", "")).startswith("CMS_")
        ],
        "evidence_strength_score": max(
            [float(citation.get("relevance_score", 0.0)) for citation in citations] or [0.0]
        ),
        "source_coverage_summary": data.get("source_coverage_summary", ""),
    }


def strategy_personal_evidence_shape(personal_evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": personal_evidence["case_id"],
        "symptoms": personal_evidence.get("symptoms", []),
        "treatment_history": personal_evidence.get("treatment_history", []),
        "prior_treatment_attempts": personal_evidence.get("prior_treatment_attempts", []),
        "treating_physician_statement": personal_evidence.get("treating_physician_statement") or "",
        "evidence_strength_score": personal_evidence.get("evidence_strength_score", 0.0),
        "gaps_found": personal_evidence.get("gaps_found", []),
    }


def strategy_denial_intake_shape(denial_intake: dict[str, Any]) -> dict[str, Any]:
    return {
        **denial_intake,
        "plan_id": denial_intake.get("plan_id") or "",
        "member_id": denial_intake.get("member_id") or "",
        "treating_physician": denial_intake.get("treating_physician") or "Not specified",
        "denial_date": denial_intake.get("denial_date") or "",
        "appeal_deadline": denial_intake.get("appeal_deadline") or "",
        "service_dates": denial_intake.get("service_dates") or [],
        "denied_procedure_codes": denial_intake.get("denied_procedure_codes") or [],
        "diagnosis_codes": denial_intake.get("diagnosis_codes") or [],
        "confidence_score": denial_intake.get("confidence_score") or 0.0,
    }


def build_strategy_input(
    denial_intake: dict[str, Any],
    personal_evidence: dict[str, Any],
    external_evidence: dict[str, Any],
    contact_actions: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    raw = {
        "denial_intake": strategy_denial_intake_shape(denial_intake),
        "personal_evidence": strategy_personal_evidence_shape(personal_evidence),
        "external_evidence": strategy_external_evidence_shape(external_evidence),
        "contact_actions": contact_actions,
    }
    return parse_input(raw)


def fallback_draft(strategy: dict[str, Any], reason: str) -> dict[str, Any]:
    recommended = strategy.get("agent_recommended_remedy", "full_overturn")
    reasoning = strategy.get("agent_recommendation_reasoning", "")
    arguments = strategy.get("argument_chain", [])
    paragraphs = [
        "To Whom It May Concern:",
        (
            "I am submitting this appeal to request reconsideration of the denial "
            f"associated with case {strategy.get('case_id', 'unknown')}."
        ),
    ]
    for argument in arguments[:3]:
        claim = argument.get("claim")
        if claim:
            paragraphs.append(str(claim))
    paragraphs.append(
        f"Requested remedy: {recommended}. {reasoning}".strip()
    )
    paragraphs.append("Sincerely,\n[Patient / Authorized Representative]")

    citations = []
    for index, violation in enumerate(strategy.get("contract_violations", [])[:5], start=1):
        citations.append(
            {
                "footnote_index": index,
                "source": violation.get("source", "strategy.contract_violations"),
                "quote": violation.get("clause", ""),
                "relevance_score": violation.get("contradiction_score", 0.0),
            }
        )

    return {
        "appeal_letter": "\n\n".join(paragraphs),
        "citations_footnoted": citations,
        "exhibits_checklist": [
            {
                "exhibit_label": "Exhibit A",
                "description": "Denial letter and plan/coverage documents",
                "required": True,
            },
            {
                "exhibit_label": "Exhibit B",
                "description": "Patient-specific medical evidence and treating physician support",
                "required": True,
            },
            {
                "exhibit_label": "Exhibit C",
                "description": "External policy and coverage citations",
                "required": True,
            },
        ],
        "submission_instructions": [
            "Review the generated appeal letter for accuracy before submission.",
            "Attach all listed exhibits and submit through the insurer appeal channel.",
        ],
        "deadline": strategy.get("appeal_deadline") or "See denial letter",
        "generation_note": f"Fallback deterministic draft used because LLM drafting failed: {reason}",
    }


StatusCallback = Callable[[dict[str, Any]], None]


def run_pipeline(
    case_input: dict[str, Any],
    output_root: Path = CASES_DIR,
    status_callback: StatusCallback | None = None,
) -> dict[str, Any]:
    load_dotenv(REPO_ROOT / "external_evidence_agent" / ".env")
    case_id = ensure_case_id(case_input)
    case_dir = output_root / case_id
    artifacts_dir = case_dir / "artifacts"

    status_log: list[dict[str, Any]] = []

    def record(step: str, status: str, artifact: str | None = None, notes: list[str] | None = None) -> None:
        entry = {
            "step": step,
            "status": status,
            "artifact": artifact,
            "notes": notes or [],
            "timestamp": utc_now(),
        }
        status_log.append(entry)
        if status_callback is not None:
            status_callback(entry)

    write_json(case_dir / "input_case.json", case_input)

    denial_intake = case_input["denial_intake"]
    missing_info_request = case_input["missing_info_request"]
    personal_evidence_task = case_input.get("personal_evidence_task", {})
    personal_evidence = case_input["personal_evidence"]
    external_evidence_task = case_input["external_evidence_task"]
    user_preferences = case_input.get("user_preferences", {})

    write_json(artifacts_dir / "denial_intake.json", denial_intake)
    write_json(artifacts_dir / "missing_info_request.json", missing_info_request)
    write_json(artifacts_dir / "personal_evidence_task.json", personal_evidence_task)
    write_json(artifacts_dir / "personal_evidence.json", personal_evidence)
    write_json(artifacts_dir / "external_evidence_task.json", external_evidence_task)
    if isinstance(user_preferences, dict) and user_preferences:
        write_json(artifacts_dir / "user_preferences.json", user_preferences)
    record("seed_golden_artifacts", "success", str(artifacts_dir))

    contact_resolved = resolve_missing_info(missing_info_request)
    contact_actions = build_contact_packet(missing_info_request, contact_resolved)
    if isinstance(user_preferences, dict) and user_preferences:
        contact_actions["user_preferences"] = user_preferences
    contact_path = artifacts_dir / "contact_actions.json"
    write_json(contact_path, contact_actions)
    record("contact_agent", "success", str(contact_path))

    external_artifact = retrieve_external_evidence(
        ExternalEvidenceTask.model_validate(external_evidence_task)
    ).model_dump(mode="json")
    external_path = artifacts_dir / "external_evidence.json"
    write_json(external_path, external_artifact)
    record("external_evidence_agent", external_artifact.get("status", "success"), str(external_path))

    strategy_input, warnings = build_strategy_input(
        denial_intake,
        personal_evidence,
        external_artifact,
        contact_actions,
    )
    strategy_input_path = artifacts_dir / "appeal_strategy_input.json"
    write_json(strategy_input_path, strategy_input)
    record("appeal_strategy_input", "success", str(strategy_input_path), warnings)

    strategy = generate_strategy(
        strategy_input["denial_intake"],
        strategy_input["personal_evidence"],
        strategy_input["external_evidence"],
        strategy_input["contact_actions"],
    )
    strategy_path = artifacts_dir / "appeal_strategy.json"
    write_json(strategy_path, strategy)
    record("appeal_strategy_agent", "success", str(strategy_path))

    try:
        drafted = draft_letter(strategy)
        draft_notes: list[str] = []
    except (JSONDecodeError, KeyError, ValueError) as exc:
        drafted = fallback_draft(strategy, f"{type(exc).__name__}: {exc}")
        draft_notes = [drafted["generation_note"]]
    drafted_path = artifacts_dir / "drafted_letter.json"
    write_json(drafted_path, drafted)
    record("drafting_agent_letter", "success", str(drafted_path), draft_notes)

    packet = build_packet(strategy, drafted)
    packet_path = artifacts_dir / "appeal_packet.json"
    write_json(packet_path, packet)
    record("drafting_agent_packet", "success", str(packet_path))

    verification_report = verify_pipeline_artifacts(
        case_id=case_id,
        denial_intake=denial_intake,
        personal_evidence=personal_evidence,
        external_evidence=external_artifact,
        contact_actions=contact_actions,
        strategy=strategy,
        drafted=drafted,
        packet=packet,
    )
    verification_path = artifacts_dir / "verification_report.json"
    write_json(verification_path, verification_report)
    record("verification", verification_report["status"], str(verification_path))

    summary = {
        "case_id": case_id,
        "status": "success",
        "case_dir": str(case_dir),
        "artifacts": {
            "denial_intake": str(artifacts_dir / "denial_intake.json"),
            "missing_info_request": str(artifacts_dir / "missing_info_request.json"),
            "personal_evidence": str(artifacts_dir / "personal_evidence.json"),
            "contact_actions": str(contact_path),
            "external_evidence": str(external_path),
            "appeal_strategy": str(strategy_path),
            "drafted_letter": str(drafted_path),
            "appeal_packet": str(packet_path),
            "verification_report": str(verification_path),
        },
        "verification_status": verification_report["status"],
        "status_log": status_log,
    }
    write_json(case_dir / "pipeline_result.json", summary)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Counterclaim local pipeline from golden JSON artifacts.")
    parser.add_argument(
        "--case",
        default=str(REPO_ROOT / "orchestrator" / "golden_cases" / "pt_tibia_rehab_case.json"),
        help="Path to golden case JSON.",
    )
    parser.add_argument(
        "--output-root",
        default=str(CASES_DIR),
        help="Directory where case artifacts should be written.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run_pipeline(load_json(Path(args.case)), output_root=Path(args.output_root))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
