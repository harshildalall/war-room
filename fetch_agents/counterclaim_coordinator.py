from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, UTC
from pathlib import Path
from typing import Any
from uuid import uuid4

import certifi

os.environ.setdefault("SSL_CERT_FILE", certifi.where())
os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())

from dotenv import load_dotenv
from uagents import Agent, Context, Protocol
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    EndSessionContent,
    StartSessionContent,
    TextContent,
    chat_protocol_spec,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASE_PATH = REPO_ROOT / "orchestrator" / "golden_cases" / "pt_tibia_rehab_case.json"

sys.path.insert(0, str(REPO_ROOT))

from orchestrator.run_pipeline import load_json, run_pipeline


asyncio.set_event_loop(asyncio.new_event_loop())

load_dotenv(REPO_ROOT / "external_evidence_agent" / ".env")
load_dotenv(Path(__file__).with_name(".env"))


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def create_text_chat(text: str, *, end_session: bool = False) -> ChatMessage:
    content: list[Any] = [TextContent(type="text", text=text)]
    if end_session:
        content.append(EndSessionContent(type="end-session"))
    return ChatMessage(
        timestamp=datetime.now(UTC),
        msg_id=uuid4(),
        content=content,
    )


def extract_text(msg: ChatMessage) -> str:
    chunks: list[str] = []
    for item in msg.content:
        if isinstance(item, TextContent):
            chunks.append(item.text)
        elif not isinstance(item, (StartSessionContent, EndSessionContent)):
            text = getattr(item, "text", None)
            if isinstance(text, str):
                chunks.append(text)
    return "\n".join(chunks).strip()


def parse_case_payload(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if not stripped.startswith("{"):
        return None
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) and "case_id" in parsed else None


def should_run_demo(text: str) -> bool:
    normalized = text.lower()
    triggers = ("demo", "sample", "golden", "test case", "run case", "appeal")
    return any(trigger in normalized for trigger in triggers)


def summarize_pipeline_result(result: dict[str, Any]) -> str:
    artifacts = result.get("artifacts", {})
    status_log = result.get("status_log", [])
    completed_steps = [entry.get("step") for entry in status_log if entry.get("status")]

    lines = [
        "Counterclaim appeal pipeline completed.",
        f"Case ID: {result.get('case_id', 'unknown')}",
        f"Pipeline status: {result.get('status', 'unknown')}",
        f"Verification status: {result.get('verification_status', 'unknown')}",
    ]

    if completed_steps:
        lines.append("Executed steps: " + ", ".join(str(step) for step in completed_steps))

    important_artifacts = [
        "external_evidence",
        "appeal_strategy",
        "drafted_letter",
        "appeal_packet",
        "verification_report",
    ]
    available = [f"{name}: {artifacts[name]}" for name in important_artifacts if name in artifacts]
    if available:
        lines.append("Key artifacts:")
        lines.extend(f"- {item}" for item in available)

    lines.append("The final appeal packet is ready for review before submission.")
    return "\n".join(lines)


def latest_demo_summary() -> str | None:
    result_path = REPO_ROOT / "cases" / "demo-pt-tibia-001" / "pipeline_result.json"
    if not result_path.exists():
        return None
    try:
        return summarize_pipeline_result(json.loads(result_path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return None


def help_text() -> str:
    return (
        "Counterclaim Coordinator is online. I can run a medical insurance appeal "
        "pipeline using JSON artifacts and return an appeal packet summary.\n\n"
        "Try one of these:\n"
        "- status\n"
        "- demo summary\n"
        "- run demo case\n\n"
        "For the fastest demo, use 'demo summary' after the local pipeline has run once."
    )


def run_counterclaim_from_text(text: str) -> str:
    normalized = text.strip().lower()
    if normalized in {"status", "ping", "hello", "help", "what can you do?"}:
        return help_text()

    if "demo summary" in normalized or "latest demo" in normalized:
        summary = latest_demo_summary()
        if summary:
            return summary
        return "No local demo artifacts found yet. Send 'run demo case' to generate them."

    case_payload = parse_case_payload(text)
    if case_payload is None:
        if not should_run_demo(text):
            return help_text()
        case_payload = load_json(DEFAULT_CASE_PATH)

    result = run_pipeline(case_payload)
    return summarize_pipeline_result(result)


AGENT_NAME = os.getenv("FETCH_AGENT_NAME", "counterclaim_coordinator")
AGENT_SEED = os.getenv("FETCH_AGENT_SEED", "counterclaim coordinator local development seed")
AGENT_PORT = int(os.getenv("FETCH_AGENT_PORT", "8010"))
AGENT_MAILBOX = env_bool("FETCH_AGENT_MAILBOX", True)

agent = Agent(
    name=AGENT_NAME,
    seed=AGENT_SEED,
    port=AGENT_PORT,
    mailbox=AGENT_MAILBOX,
    publish_agent_details=True,
    readme_path=str(Path(__file__).with_name("README.md")),
)

chat_proto = Protocol(spec=chat_protocol_spec)


@chat_proto.on_message(ChatMessage)
async def handle_chat_message(ctx: Context, sender: str, msg: ChatMessage) -> None:
    await ctx.send(
        sender,
        ChatAcknowledgement(
            timestamp=datetime.now(UTC),
            acknowledged_msg_id=msg.msg_id,
        ),
    )

    text = extract_text(msg)
    if not text:
        await ctx.send(sender, create_text_chat("Send case JSON or ask me to run the demo case."))
        return

    ctx.logger.info("Received Counterclaim chat request from %s", sender)
    try:
        response_text = await asyncio.to_thread(run_counterclaim_from_text, text)
    except Exception as exc:
        ctx.logger.exception("Counterclaim pipeline failed")
        response_text = (
            "Counterclaim pipeline failed while processing this request. "
            f"Error: {type(exc).__name__}: {exc}"
        )

    await ctx.send(sender, create_text_chat(response_text, end_session=True))


@chat_proto.on_message(ChatAcknowledgement)
async def handle_chat_ack(ctx: Context, sender: str, msg: ChatAcknowledgement) -> None:
    ctx.logger.info("Chat acknowledgement from %s for %s", sender, msg.acknowledged_msg_id)


agent.include(chat_proto)


if __name__ == "__main__":
    print(f"Counterclaim Fetch agent address: {agent.address}")
    print(f"Agentverse inspector should be shown by uAgents on port {AGENT_PORT}.")
    agent.run()
