import json

REQUIRED_STRATEGY_KEYS = [
    "case_id",
    "argument_chain",
    "strongest_arguments",
    "contract_violations",
    "recommended_remedy",
    "confidence_score",
    "denial_linked_to_patient_facts",
    "denial_linked_to_policy",
]

def load_strategy(path: str) -> dict:
    with open(path) as f:
        strategy = json.load(f)
    missing = [k for k in REQUIRED_STRATEGY_KEYS if k not in strategy]
    if missing:
        raise ValueError(f"appeal_strategy.json missing required keys: {missing}")
    return strategy