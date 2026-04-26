from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from query_planner import build_queries, dedupe_queries, extract_codes, preferred_source_types
from schemas import EvidenceQuery, ExternalEvidenceTask, QueryStrategy, SourceType


AGENT_DIR = Path(__file__).resolve().parent
SOURCE_TYPE_ALIASES = {
    "cms ncd": "CMS_NCD",
    "cms_ncd": "CMS_NCD",
    "ncd": "CMS_NCD",
    "cms lcd": "CMS_LCD",
    "cms_lcd": "CMS_LCD",
    "lcd": "CMS_LCD",
    "cms manual": "CMS_MANUAL",
    "cms_manual": "CMS_MANUAL",
    "manual": "CMS_MANUAL",
    "insurer policy": "INSURER_POLICY",
    "insurer_policy": "INSURER_POLICY",
    "payer policy": "INSURER_POLICY",
    "policy": "INSURER_POLICY",
    "specialty guideline": "SPECIALTY_GUIDELINE",
    "specialty guidelines": "SPECIALTY_GUIDELINE",
    "specialty_guideline": "SPECIALTY_GUIDELINE",
    "guideline": "SPECIALTY_GUIDELINE",
    "guidelines": "SPECIALTY_GUIDELINE",
    "appeals precedent": "APPEALS_PRECEDENT",
    "appeals_precedent": "APPEALS_PRECEDENT",
    "precedent": "APPEALS_PRECEDENT",
    "other": "OTHER",
}
STRATEGY_ALIASES = {
    "exact code": "exact_code",
    "exact_code": "exact_code",
    "code": "exact_code",
    "semantic": "semantic",
    "hybrid": "hybrid",
    "policy lookup": "policy_lookup",
    "policy_lookup": "policy_lookup",
    "policy": "policy_lookup",
    "manual": "manual",
    "manual lookup": "manual",
}


class QueryPlan(BaseModel):
    queries: list[EvidenceQuery]
    mode: str
    notes: list[str] = Field(default_factory=list)


class LLMQueryIntent(BaseModel):
    query: str
    strategy: QueryStrategy
    source_types: list[SourceType] = Field(default_factory=list)
    codes: list[str] = Field(default_factory=list)
    rationale: str | None = None


class LLMQueryResponse(BaseModel):
    queries: list[LLMQueryIntent] = Field(default_factory=list, max_length=8)


def build_query_plan(task: ExternalEvidenceTask, top_k: int = 8) -> QueryPlan:
    deterministic = build_queries(task, top_k=top_k)
    llm_queries, notes = generate_llm_queries(task, top_k=top_k)

    if not llm_queries:
        return QueryPlan(queries=deterministic, mode="deterministic", notes=notes)

    combined = dedupe_queries([*llm_queries, *deterministic])
    notes.append("LLM-generated retrieval intents were prepended; deterministic queries were appended as backup.")
    return QueryPlan(queries=combined, mode="llm_plus_deterministic", notes=notes)


def generate_llm_queries(task: ExternalEvidenceTask, top_k: int = 8) -> tuple[list[EvidenceQuery], list[str]]:
    load_dotenv(AGENT_DIR / ".env")
    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    model = os.getenv("LLM_MODEL", "").strip()
    if not provider:
        return [], ["LLM query generation skipped because LLM_PROVIDER is not configured."]
    if not model:
        return [], ["LLM query generation skipped because LLM_MODEL is not configured."]

    prompt = build_prompt(task)
    try:
        if provider == "anthropic":
            raw = call_anthropic(prompt, model)
        elif provider == "openai":
            raw = call_openai(prompt, model)
        else:
            return [], [f"LLM query generation skipped because provider '{provider}' is unsupported."]
    except Exception as exc:
        return [], [f"LLM query generation failed; deterministic queries used. Error: {type(exc).__name__}"]

    try:
        response = parse_llm_response(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        return [], [f"LLM query generation returned invalid JSON; deterministic queries used. Error: {type(exc).__name__}"]

    queries = normalize_llm_queries(task, response.queries, top_k=top_k)
    if not queries:
        return [], ["LLM query generation returned no usable queries; deterministic queries used."]
    return queries, [f"LLM query generation used provider '{provider}' with configured model."]


def build_prompt(task: ExternalEvidenceTask) -> str:
    payload = task.model_dump(mode="json")
    allowed_source_types = [
        "CMS_NCD",
        "CMS_LCD",
        "CMS_MANUAL",
        "INSURER_POLICY",
        "SPECIALTY_GUIDELINE",
        "APPEALS_PRECEDENT",
        "OTHER",
    ]
    allowed_strategies = ["exact_code", "semantic", "hybrid", "policy_lookup", "manual"]
    return f"""
You generate retrieval intents for a health insurance appeal evidence search.

The agent has a curated MongoDB corpus of validated payer/CMS/guideline sources.
You must not invent citations, laws, source titles, quotes, URLs, or coverage conclusions.
Only generate search intents that could retrieve citation-backed evidence from the corpus.

Prefer intents that test:
- whether the denied service/code is covered or medically necessary
- whether the insurer's own policy supports rehabilitation or physical therapy
- whether CMS LCD/manual language supports skilled therapy, plan of care, and functional improvement
- whether clinical terms should be expanded for fracture rehabilitation and therapeutic exercise

Allowed strategies: {allowed_strategies}
Allowed source_types: {allowed_source_types}

Return only valid JSON in this exact shape. Do not wrap it in Markdown:
{{
  "queries": [
    {{
      "query": "search phrase",
      "strategy": "hybrid",
      "source_types": ["INSURER_POLICY", "CMS_LCD"],
      "codes": ["97110"],
      "rationale": "short reason this query helps"
    }}
  ]
}}

Task JSON:
{json.dumps(payload, indent=2)}
""".strip()


def call_anthropic(prompt: str, model: str) -> str:
    from anthropic import Anthropic

    client = Anthropic()
    message = client.messages.create(
        model=model,
        max_tokens=1200,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    parts = []
    for block in message.content:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts)


def call_openai(prompt: str, model: str) -> str:
    from openai import OpenAI

    client = OpenAI()
    response = client.responses.create(
        model=model,
        input=prompt,
        temperature=0,
    )
    return response.output_text


def extract_json_object(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in LLM response.")
    return text[start : end + 1]


def parse_llm_response(raw: str) -> LLMQueryResponse:
    payload = json.loads(extract_json_object(raw))
    if isinstance(payload, list):
        raw_queries = payload
    elif isinstance(payload, dict):
        raw_queries = (
            payload.get("queries")
            or payload.get("retrieval_intents")
            or payload.get("intents")
            or payload.get("evidence_queries")
            or []
        )
    else:
        raise ValueError("LLM response must be a JSON object or list.")

    if not isinstance(raw_queries, list):
        raise ValueError("LLM response queries field must be a list.")

    intents: list[LLMQueryIntent] = []
    for raw_query in raw_queries[:8]:
        if not isinstance(raw_query, dict):
            continue
        query_text = raw_query.get("query") or raw_query.get("query_text") or raw_query.get("search_query")
        if not isinstance(query_text, str) or not query_text.strip():
            continue

        strategy = normalize_strategy(raw_query.get("strategy"))
        source_types = normalize_source_types(raw_query.get("source_types") or raw_query.get("sources"))
        codes = normalize_codes(raw_query.get("codes"))
        rationale = raw_query.get("rationale") or raw_query.get("reason")

        intents.append(
            LLMQueryIntent(
                query=query_text,
                strategy=strategy,
                source_types=source_types,
                codes=codes,
                rationale=rationale if isinstance(rationale, str) else None,
            )
        )

    return LLMQueryResponse(queries=intents)


def normalize_strategy(value: Any) -> QueryStrategy:
    if isinstance(value, str):
        normalized = value.strip().lower().replace("-", "_")
        normalized = STRATEGY_ALIASES.get(normalized, normalized)
        if normalized in {"exact_code", "semantic", "hybrid", "policy_lookup", "manual"}:
            return normalized  # type: ignore[return-value]
    return "hybrid"


def normalize_source_types(value: Any) -> list[SourceType]:
    if not value:
        return []
    values = value if isinstance(value, list) else [value]
    normalized: list[SourceType] = []
    for item in values:
        if not isinstance(item, str):
            continue
        key = item.strip().lower().replace("-", "_")
        source_type = SOURCE_TYPE_ALIASES.get(key, item.strip().upper().replace(" ", "_").replace("-", "_"))
        if source_type in {
            "CMS_NCD",
            "CMS_LCD",
            "CMS_MANUAL",
            "INSURER_POLICY",
            "SPECIALTY_GUIDELINE",
            "APPEALS_PRECEDENT",
            "OTHER",
        } and source_type not in normalized:
            normalized.append(source_type)  # type: ignore[arg-type]
    return normalized


def normalize_codes(value: Any) -> list[str]:
    if not value:
        return []
    values = value if isinstance(value, list) else [value]
    codes: list[str] = []
    for item in values:
        code = str(item).strip().upper()
        if code and code not in codes:
            codes.append(code)
    return codes


def normalize_llm_queries(
    task: ExternalEvidenceTask,
    intents: list[LLMQueryIntent],
    top_k: int,
) -> list[EvidenceQuery]:
    task_codes = extract_codes(task)
    fallback_source_types = preferred_source_types(task)
    normalized: list[EvidenceQuery] = []

    for intent in intents:
        query_text = " ".join(intent.query.split())
        if len(query_text) < 3:
            continue

        codes = [code.strip().upper() for code in intent.codes if code.strip()]
        if not codes:
            codes = task_codes

        source_types = intent.source_types or fallback_source_types
        normalized.append(
            EvidenceQuery(
                query=query_text,
                strategy=intent.strategy,
                top_k=top_k,
                codes=codes,
                source_types=source_types,
                insurer=task.insurer,
                rationale=intent.rationale,
            )
        )

    return dedupe_queries(normalized)
