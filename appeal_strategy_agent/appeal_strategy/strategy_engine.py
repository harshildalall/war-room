"""Appeal Strategy engine.

Synthesizes the four upstream agent outputs (denial intake, personal evidence,
external evidence, contact actions) into a structured appeal strategy by
calling Claude Sonnet 4.6 with prompt caching and a forced tool call.

Adds a file-based response cache keyed on the md5 of all four inputs so that
re-running the same case is free. Set SKIP_CACHE=1 to bypass.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4096
TOOL_NAME = "submit_strategy"

PACKAGE_DIR = Path(__file__).resolve().parent
PROMPTS_DIR = PACKAGE_DIR / "prompts"
SYSTEM_PROMPT_PATH = PROMPTS_DIR / "system_prompt.txt"
TOOL_SCHEMA_PATH = PROMPTS_DIR / "strategy_tool.json"

CACHE_DIR = PACKAGE_DIR.parent / ".cache"


class StrategyEngineError(Exception):
    pass


def _load_system_prompt() -> str:
    text = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()
    if not text:
        raise StrategyEngineError(
            f"System prompt at {SYSTEM_PROMPT_PATH} is empty."
        )
    return text


def _load_tool_schema() -> dict[str, Any]:
    raw = TOOL_SCHEMA_PATH.read_text(encoding="utf-8").strip()
    if not raw:
        raise StrategyEngineError(
            f"Tool schema at {TOOL_SCHEMA_PATH} is empty."
        )
    try:
        schema = json.loads(raw)
    except json.JSONDecodeError as e:
        raise StrategyEngineError(
            f"Tool schema at {TOOL_SCHEMA_PATH} is not valid JSON: {e}"
        ) from e
    if schema.get("name") != TOOL_NAME:
        raise StrategyEngineError(
            f"Tool schema name must be '{TOOL_NAME}', got {schema.get('name')!r}."
        )
    return schema


def _build_client() -> Anthropic:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise StrategyEngineError(
            "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and fill it in."
        )
    return Anthropic(api_key=api_key)


def _hash_inputs(
    denial_intake: dict[str, Any],
    personal_evidence: dict[str, Any],
    external_evidence: dict[str, Any],
    contact_actions: dict[str, Any],
) -> str:
    combined = json.dumps(
        {
            "denial_intake": denial_intake,
            "personal_evidence": personal_evidence,
            "external_evidence": external_evidence,
            "contact_actions": contact_actions,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.md5(combined.encode("utf-8")).hexdigest()


def _cache_path(input_hash: str) -> Path:
    return CACHE_DIR / f"{input_hash}.json"


def _load_cached(input_hash: str) -> dict[str, Any] | None:
    path = _cache_path(input_hash)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _store_cached(input_hash: str, response: dict[str, Any]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _cache_path(input_hash).write_text(
        json.dumps(response, indent=2, default=str), encoding="utf-8"
    )


def _build_user_message(
    denial_intake: dict[str, Any],
    personal_evidence: dict[str, Any],
    external_evidence: dict[str, Any],
    contact_actions: dict[str, Any],
) -> str:
    def block(tag: str, payload: dict[str, Any]) -> str:
        return f"<{tag}>\n{json.dumps(payload, indent=2, default=str)}\n</{tag}>"

    return "\n\n".join(
        [
            block("denial_intake", denial_intake),
            block("personal_evidence", personal_evidence),
            block("external_evidence", external_evidence),
            block("contact_actions", contact_actions),
        ]
    )


def _call_claude(
    denial_intake: dict[str, Any],
    personal_evidence: dict[str, Any],
    external_evidence: dict[str, Any],
    contact_actions: dict[str, Any],
) -> dict[str, Any]:
    system_prompt = _load_system_prompt()
    tool_schema = _load_tool_schema()
    client = _build_client()

    user_message = _build_user_message(
        denial_intake, personal_evidence, external_evidence, contact_actions
    )

    message = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=[
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        tools=[tool_schema],
        tool_choice={"type": "tool", "name": TOOL_NAME},
        messages=[{"role": "user", "content": user_message}],
    )

    tool_use = next(
        (b for b in message.content if b.type == "tool_use"),
        None,
    )
    if tool_use is None:
        raise StrategyEngineError(
            "Model did not return a tool_use block despite forced tool_choice. "
            f"stop_reason={message.stop_reason!r}."
        )

    result = dict(tool_use.input)

    required_fields = tool_schema["input_schema"].get("required", [])
    missing = [f for f in required_fields if f not in result]
    if missing:
        raise StrategyEngineError(
            f"Model response is missing required fields: {missing}. "
            f"stop_reason={message.stop_reason!r}"
            + (
                " (output was truncated — increase MAX_TOKENS or further "
                "tighten the schema/prompt)."
                if message.stop_reason == "max_tokens"
                else "."
            )
        )

    return result


def generate_strategy(
    denial_intake: dict[str, Any],
    personal_evidence: dict[str, Any],
    external_evidence: dict[str, Any],
    contact_actions: dict[str, Any],
) -> dict[str, Any]:
    """Generate a structured appeal strategy from the four upstream inputs.

    Caches the response on disk keyed on md5(all four inputs). Set SKIP_CACHE=1
    in the environment to bypass.
    """
    skip_cache = os.getenv("SKIP_CACHE") == "1"
    input_hash = _hash_inputs(
        denial_intake, personal_evidence, external_evidence, contact_actions
    )

    if not skip_cache:
        cached = _load_cached(input_hash)
        if cached is not None:
            return cached

    strategy = _call_claude(
        denial_intake, personal_evidence, external_evidence, contact_actions
    )

    if not skip_cache:
        _store_cached(input_hash, strategy)

    return strategy


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print(
            "Usage: python -m appeal_strategy.strategy_engine <combined_inputs.json>",
            file=sys.stderr,
        )
        raise SystemExit(2)

    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    result = generate_strategy(
        payload["denial_intake"],
        payload["personal_evidence"],
        payload["external_evidence"],
        payload["contact_actions"],
    )
    print(json.dumps(result, indent=2))
