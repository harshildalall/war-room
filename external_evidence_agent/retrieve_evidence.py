from __future__ import annotations

import argparse
import json
from pathlib import Path

from retrieval import load_task, retrieve_external_evidence


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Retrieve citation-backed external evidence for a task JSON.")
    parser.add_argument("task_json", help="Path to external_evidence_task.json")
    parser.add_argument("--top-k", type=int, default=8, help="Maximum citations to return.")
    parser.add_argument("--json", action="store_true", help="Print full JSON artifact.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    artifact = retrieve_external_evidence(load_task(Path(args.task_json)), top_k=args.top_k)
    if args.json:
        print(json.dumps(artifact.model_dump(mode="json"), indent=2))
        return

    print(f"case_id={artifact.case_id}")
    print(f"status={artifact.status}")
    print(f"summary={artifact.data.source_coverage_summary}")
    for citation in artifact.data.citations:
        print(
            f"{citation.citation_id} score={citation.relevance_score:.3f} "
            f"authority={citation.authority_score:.2f} source={citation.citation.citation_label}"
        )


if __name__ == "__main__":
    main()
