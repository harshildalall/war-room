"""Local CLI test harness for the Appeal Strategy Agent.

Reads a single combined-input JSON file containing the four upstream payloads:

    {
      "denial_intake":     {...},
      "personal_evidence": {...},
      "external_evidence": {...},
      "contact_actions":   {...}
    }

Calls generate_strategy and pretty-prints the result with a short summary.

Usage:
    python -m appeal_strategy.tests.test_local <path-to-case.json>
    SKIP_CACHE=1 python -m appeal_strategy.tests.test_local <path-to-case.json>
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import argparse
import json

from strategy_engine import (
    StrategyEngineError,
    generate_strategy,
)

REQUIRED_KEYS = (
    "denial_intake",
    "personal_evidence",
    "external_evidence",
    "contact_actions",
)

OUTPUTS_DIR = Path(__file__).resolve().parent.parent.parent / "outputs"

TRACE_FIELDS = (
    "case_id",
    "argument_chain",
    "agent_recommended_remedy",
    "agent_recommendation_reasoning",
)


def _load_case(path: Path) -> dict | None:
    if not path.exists():
        print(f"error: file not found: {path}", file=sys.stderr)
        return None
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        print(f"error: file is empty: {path}", file=sys.stderr)
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"error: invalid JSON in {path}: {e}", file=sys.stderr)
        return None

    missing = [k for k in REQUIRED_KEYS if k not in data]
    if missing:
        print(
            f"error: {path} is missing required top-level keys: {missing}",
            file=sys.stderr,
        )
        return None

    return data


def _print_summary(strategy: dict) -> None:
    print("\n--- summary ---")
    print(f"case_id:         {strategy.get('case_id')}")
    print(f"argument count:  {len(strategy.get('argument_chain', []))}")
    print(f"violation count: {len(strategy.get('contract_violations', []))}")

    options = strategy.get("remedy_options", []) or []
    pick = strategy.get("agent_recommended_remedy")

    print(f"\n--- remedy options ({len(options)}) ---")
    for i, opt in enumerate(options, 1):
        rtype = opt.get("remedy_type")
        marker = "  <-- RECOMMENDED" if rtype == pick else ""
        recovery = opt.get("estimated_recovery_amount")
        recovery_str = (
            f"${recovery:,.2f}" if isinstance(recovery, (int, float)) else "n/a"
        )
        print(f"\n[{i}] {rtype}{marker}")
        print(f"    confidence:    {opt.get('confidence_score')}")
        print(f"    timeline:      {opt.get('estimated_timeline_days')} days")
        print(f"    est. recovery: {recovery_str}")
        primary = opt.get("primary_argument")
        if primary:
            print(f"    primary arg:   {primary}")
        idx = opt.get("supporting_argument_indices") or []
        if idx:
            print(f"    arg indices:   {idx}")
        risks = opt.get("key_risks") or []
        if risks:
            print(f"    key risks:")
            for r in risks:
                print(f"      - {r}")

    print(f"\n--- agent recommends: {pick} ---")
    reasoning = strategy.get("agent_recommendation_reasoning")
    if reasoning:
        print(f"reasoning: {reasoning}")


def _save_outputs(case_path: Path, strategy: dict) -> None:
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    stem = case_path.stem
    strategy_path = OUTPUTS_DIR / f"{stem}_strategy.json"
    trace_path = OUTPUTS_DIR / f"{stem}_trace.json"

    trace = {k: strategy.get(k) for k in TRACE_FIELDS if k in strategy}

    strategy_path.write_text(
        json.dumps(strategy, indent=2) + "\n", encoding="utf-8"
    )
    trace_path.write_text(json.dumps(trace, indent=2) + "\n", encoding="utf-8")

    print(f"\n--- saved ---")
    print(f"strategy: {strategy_path}")
    print(f"trace:    {trace_path}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the strategy engine against a combined-input case file."
    )
    parser.add_argument("case_file", help="Path to a case_XX_input.json file.")
    args = parser.parse_args()

    case = _load_case(Path(args.case_file))
    if case is None:
        return 2

    try:
        strategy = generate_strategy(
            case["denial_intake"],
            case["personal_evidence"],
            case["external_evidence"],
            case["contact_actions"],
        )
    except StrategyEngineError as e:
        print(f"engine error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"unexpected error: {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    print(json.dumps(strategy, indent=2))
    _print_summary(strategy)
    _save_outputs(Path(args.case_file), strategy)
    return 0


if __name__ == "__main__":
    sys.exit(main())
